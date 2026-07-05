import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import httpx
import pytz
import html
from .config import settings

SOCIAL_DOMAINS = ["dcard.tw", "ptt.cc", "pttweb.cc", "threads.net", "threads.com", "instagram.com"]

def send_daily_news_email(news_items, date_str: str):
    # Query database for custom recipient email
    from .database import SessionLocal
    from . import models
    
    db = SessionLocal()
    setting = None
    try:
        setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "email_recipient").first()
    except Exception as e:
        print(f"[Mailer] Error querying recipient list from DB: {e}")
    finally:
        db.close()
        
    recipients = []
    if setting is None:
        if settings.EMAIL_RECIPIENT:
            recipients = [settings.EMAIL_RECIPIENT.strip()]
    else:
        if setting.value:
            recipients = [e.strip() for e in setting.value.split(",") if e.strip()]

    if not recipients:
        print("[Mailer] No recipient emails configured. Skipping email sending.")
        return False, "No recipient emails configured"

    # Send mail to all recipients
    success_count = 0
    results = []
    for recipient in recipients:
        if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
            print(f"[Mailer] Sending daily news email to {recipient} via SMTP...")
            success, msg = send_via_smtp(news_items, date_str, recipient)
        else:
            print(f"[Mailer] Sending daily news email to {recipient} via FormSubmit.co AJAX fallback...")
            success, msg = send_via_formsubmit(news_items, date_str, recipient)
        
        if success:
            success_count += 1
        results.append(f"{recipient}: {msg}")
        
    overall_success = success_count > 0
    overall_msg = "; ".join(results)
    return overall_success, overall_msg

def send_via_formsubmit(news_items, date_str: str, recipient: str):
    url = f"https://formsubmit.co/ajax/{recipient}"
    
    # Split list into news and social
    SOCIAL_SOURCES = ["dcard", "ptt", "threads", "instagram"]
    news_list = []
    social_list = []
    for item in news_items:
        url_lower = item.url.lower() if item.url else ""
        source_lower = item.source.lower() if item.source else ""
        is_social = any(domain in url_lower for domain in SOCIAL_DOMAINS) or \
                    any(src in source_lower for src in SOCIAL_SOURCES)
        if is_social:
            social_list.append(item)
        else:
            news_list.append(item)
            
    payload = {
        "監測狀態": "正常運作中",
        "監測日期": date_str,
        "_template": "table"
    }

    # Format News section
    if not news_list:
        payload["新聞媒體報導"] = "今日未監測到任何媒體新聞。"
    else:
        news_lines = []
        for i, item in enumerate(news_list, 1):
            pub_time = item.publish_time.strftime("%H:%M") if hasattr(item.publish_time, 'strftime') else str(item.publish_time)
            news_lines.append(f"{i}. [{item.source}] {item.title}\n   時間: {pub_time} | 關鍵字: {item.keyword}\n   連結: {item.url}")
        payload["新聞媒體報導"] = "\n\n".join(news_lines)

    # Format Social/Forum section
    if not social_list:
        payload["社群與網路論壇"] = "今日未監測到任何社群貼文或論壇討論。"
    else:
        social_lines = []
        for i, item in enumerate(social_list, 1):
            pub_time = item.publish_time.strftime("%H:%M") if hasattr(item.publish_time, 'strftime') else str(item.publish_time)
            social_lines.append(f"{i}. [{item.source}] {item.title}\n   時間: {pub_time} | 關鍵字: {item.keyword}\n   連結: {item.url}")
        payload["社群與網路論壇"] = "\n\n".join(social_lines)

    payload["_subject"] = f"【國北教大輿情日報】{date_str} - 新聞 {len(news_list)} 則 | 社群 {len(social_list)} 則"
        
    try:
        headers = {
            "Accept": "application/json",
            "Referer": "https://ntue-news-bulletin.vercel.app",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = httpx.post(url, json=payload, headers=headers, timeout=15.0)
        if response.status_code == 200:
            msg = f"Success from FormSubmit: {response.text}"
            print(f"[Mailer] {msg}")
            return True, msg
        else:
            msg = f"FormSubmit returned error status {response.status_code}: {response.text}"
            print(f"[Mailer] {msg}")
            return False, msg
    except Exception as e:
        msg = f"Exception sending via FormSubmit: {str(e)}"
        print(f"[Mailer] {msg}")
        return False, msg

def send_via_smtp(news_items, date_str: str, recipient: str):
    # Split list into news and social
    SOCIAL_SOURCES = ["dcard", "ptt", "threads", "instagram"]
    news_list = []
    social_list = []
    for item in news_items:
        url_lower = item.url.lower() if item.url else ""
        source_lower = item.source.lower() if item.source else ""
        is_social = any(domain in url_lower for domain in SOCIAL_DOMAINS) or \
                    any(src in source_lower for src in SOCIAL_SOURCES)
        if is_social:
            social_list.append(item)
        else:
            news_list.append(item)

    # 1. Build Traditional News HTML Section
    if not news_list:
        news_html = """
        <div class="empty-state">
          <p style="margin: 0; font-size: 13px; color: #64748b;">今日未監測到傳統媒體新聞報導。</p>
        </div>
        """
    else:
        rows = []
        for item in news_list:
            pub_time = item.publish_time.strftime("%H:%M") if hasattr(item.publish_time, 'strftime') else str(item.publish_time)
            escaped_url = html.escape(item.url)
            rows.append(f"""
            <tr>
              <td>
                <div><a href="{escaped_url}" class="news-title" target="_blank">{item.title}</a></div>
                <span class="badge badge-keyword" style="margin-top: 4px;">{item.keyword}</span>
              </td>
              <td style="white-space: nowrap;">
                <span class="badge badge-source">{item.source}</span>
              </td>
              <td style="white-space: nowrap; color: #64748b;">
                {pub_time}
              </td>
            </tr>
            """)
        
        news_html = f"""
        <table class="news-table">
          <thead>
            <tr>
              <th>新聞標題 / 關鍵字</th>
              <th style="width: 100px;">媒體來源</th>
              <th style="width: 80px;">時間</th>
            </tr>
          </thead>
          <tbody>
            {"".join(rows)}
          </tbody>
        </table>
        """

    # 2. Build Social/Forum HTML Section
    if not social_list:
        social_html = """
        <div class="empty-state" style="background-color: #faf5ff;">
          <p style="margin: 0; font-size: 13px; color: #7c3aed;">今日未監測到社群或網路論壇貼文。</p>
        </div>
        """
    else:
        rows = []
        for item in social_list:
            pub_time = item.publish_time.strftime("%H:%M") if hasattr(item.publish_time, 'strftime') else str(item.publish_time)
            escaped_url = html.escape(item.url)
            rows.append(f"""
            <tr>
              <td>
                <div><a href="{escaped_url}" class="news-title" style="color: #6d28d9;" target="_blank">{item.title}</a></div>
                <span class="badge badge-keyword" style="margin-top: 4px; background-color: #f5f3ff; color: #5b21b6; border-color: #ddd6fe;">{item.keyword}</span>
              </td>
              <td style="white-space: nowrap;">
                <span class="badge badge-social">{item.source}</span>
              </td>
              <td style="white-space: nowrap; color: #64748b;">
                {pub_time}
              </td>
            </tr>
            """)
        
        social_html = f"""
        <table class="news-table">
          <thead>
            <tr>
              <th>貼文標題 / 關鍵字</th>
              <th style="width: 100px;">來源平台</th>
              <th style="width: 80px;">時間</th>
            </tr>
          </thead>
          <tbody>
            {"".join(rows)}
          </tbody>
        </table>
        """

    # Load full HTML template
    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      line-height: 1.6;
      color: #1e293b;
      background-color: #f8fafc;
      margin: 0;
      padding: 0;
    }}
    .container {{
      max-width: 600px;
      margin: 20px auto;
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }}
    .header {{
      background-color: #1d2a4a;
      color: #ffffff;
      padding: 24px;
      text-align: center;
    }}
    .header h1 {{
      margin: 0;
      font-size: 20px;
      font-weight: 700;
      letter-spacing: 0.05em;
    }}
    .header p {{
      margin: 4px 0 0 0;
      font-size: 13px;
      color: #cbd5e1;
    }}
    .content {{
      padding: 24px;
    }}
    .section-title {{
      font-size: 15px;
      font-weight: 700;
      padding-bottom: 6px;
      margin-top: 0;
      margin-bottom: 12px;
    }}
    .empty-state {{
      text-align: center;
      padding: 30px 20px;
      background-color: #f1f5f9;
      border-radius: 8px;
      color: #64748b;
    }}
    .news-table {{
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 24px;
    }}
    .news-table th {{
      text-align: left;
      padding: 10px 12px;
      font-size: 11px;
      font-weight: 700;
      color: #475569;
      background-color: #f1f5f9;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .news-table td {{
      padding: 14px 12px;
      border-bottom: 1px solid #e2e8f0;
      font-size: 13px;
      vertical-align: top;
    }}
    .news-title {{
      font-weight: 600;
      color: #1d2a4a;
      text-decoration: none;
    }}
    .news-title:hover {{
      text-decoration: underline;
    }}
    .badge {{
      display: inline-block;
      padding: 2px 6px;
      font-size: 10px;
      font-weight: 600;
      border-radius: 4px;
      border: 1px solid;
    }}
    .badge-keyword {{
      background-color: #eff6ff;
      color: #1e40af;
      border-color: #bfdbfe;
    }}
    .badge-source {{
      background-color: #f0fdf4;
      color: #166534;
      border-color: #bbf7d0;
    }}
    .badge-social {{
      background-color: #faf5ff;
      color: #6b21a8;
      border-color: #e9d5ff;
    }}
    .footer {{
      background-color: #f8fafc;
      padding: 16px;
      text-align: center;
      font-size: 11px;
      color: #94a3b8;
      border-top: 1px solid #e2e8f0;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>國北教大新聞與社群監測日報</h1>
      <p>監測日期：{date_str}</p>
    </div>
    <div class="content">
      <!-- News Section -->
      <h2 class="section-title" style="color: #1d2a4a; border-bottom: 2px solid #1d2a4a;">📰 新聞媒體報導 ({len(news_list)} 則)</h2>
      {news_html}
      
      <!-- Social Section -->
      <h2 class="section-title" style="color: #6b21a8; border-bottom: 2px solid #6b21a8; margin-top: 32px;">💬 社群輿情與網路論壇 ({len(social_list)} 則)</h2>
      {social_html}
    </div>
    <div class="footer">
      本信件由國北教大輿情公佈欄系統自動發送。請勿直接回覆。
    </div>
  </div>
</body>
</html>"""

    # Plain text version fallback
    plain_text = f"國北教大新聞與社群監測日報 ({date_str})\n\n"
    
    plain_text += f"📰 傳統新聞媒體報導 ({len(news_list)} 則)：\n"
    if not news_list:
        plain_text += "今日無最新新聞。\n"
    else:
        for item in news_list:
            plain_text += f"- [{item.source}] {item.title} ({item.url})\n"
            
    plain_text += f"\n💬 社群輿情與網路論壇 ({len(social_list)} 則)：\n"
    if not social_list:
        plain_text += "今日無社群貼文或論壇討論。\n"
    else:
        for item in social_list:
            plain_text += f"- [{item.source}] {item.title} ({item.url})\n"

    # 2. Setup Vercel SMTP relay details
    relay_url = "https://ntue-news-bulletin.vercel.app/api/send-email"
    payload = {
        "secret": "ntue1234",
        "smtp_host": settings.SMTP_HOST,
        "smtp_port": settings.SMTP_PORT,
        "smtp_username": settings.SMTP_USERNAME,
        "smtp_password": settings.SMTP_PASSWORD,
        "to": recipient,
        "subject": f"【國北教大輿情日報】{date_str} - 新聞 {len(news_list)} 則 | 社群 {len(social_list)} 則",
        "text": plain_text,
        "html": html_body
    }

    try:
        response = httpx.post(relay_url, json=payload, timeout=25.0)
        if response.status_code == 200:
            res_data = response.json()
            msg_str = f"Daily news email sent successfully via Vercel SMTP relay (Message ID: {res_data.get('messageId')}) to {recipient}!"
            print(f"[Mailer] {msg_str}")
            return True, msg_str
        else:
            err_data = {}
            try:
                err_data = response.json()
            except:
                pass
            err_msg = err_data.get("error", response.text)
            msg_str = f"Vercel SMTP relay returned error status {response.status_code}: {err_msg}"
            print(f"[Mailer] {msg_str}")
            return False, msg_str
    except Exception as e:
        msg_str = f"Failed to send email via Vercel SMTP relay to {recipient}: {str(e)}"
        print(f"[Mailer] {msg_str}")
        return False, msg_str
