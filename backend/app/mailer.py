import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import httpx
import pytz
from .config import settings

def send_daily_news_email(news_items, date_str: str):
    # Check if recipient is configured
    if not settings.EMAIL_RECIPIENT:
        print("[Mailer] EMAIL_RECIPIENT not configured. Skipping email sending.")
        return False

    # Option A: If SMTP credentials are configured, use SMTP
    if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
        print(f"[Mailer] Sending daily news email to {settings.EMAIL_RECIPIENT} via SMTP...")
        return send_via_smtp(news_items, date_str)
    
    # Option B: Otherwise, use FormSubmit.co AJAX API (No credentials needed!)
    else:
        print(f"[Mailer] Sending daily news email to {settings.EMAIL_RECIPIENT} via FormSubmit.co AJAX fallback...")
        return send_via_formsubmit(news_items, date_str)

def send_via_formsubmit(news_items, date_str: str):
    url = f"https://formsubmit.co/ajax/{settings.EMAIL_RECIPIENT}"
    
    if not news_items:
        payload = {
            "監測狀態": "今日未監測到任何相關新聞報導。",
            "最新新聞數量": "0 則",
            "_subject": f"【國北教大輿情日報】{date_str} - 今日無新聞",
            "_template": "box"
        }
    else:
        news_lines = []
        for i, item in enumerate(news_items, 1):
            pub_time = item.publish_time.strftime("%H:%M") if hasattr(item.publish_time, 'strftime') else str(item.publish_time)
            news_lines.append(
                f"{i}. [{item.source}] {item.title}\n"
                f"   時間: {pub_time} | 關鍵字: {item.keyword}\n"
                f"   新聞連結: {item.url}"
            )
        
        payload = {
            "監測狀態": "正常運作中",
            "今日新聞總數": f"{len(news_items)} 則",
            "輿情報導清單": "\n\n".join(news_lines),
            "_subject": f"【國北教大輿情日報】{date_str} - 共 {len(news_items)} 則新聞",
            "_template": "table"
        }
        
    try:
        response = httpx.post(url, json=payload, headers={"Accept": "application/json"}, timeout=15.0)
        if response.status_code == 200:
            print("[Mailer] Daily news email successfully sent via FormSubmit.co!")
            return True
        else:
            print(f"[Mailer] FormSubmit.co returned error status: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"[Mailer] Failed to send via FormSubmit.co: {e}")
        return False

def send_via_smtp(news_items, date_str: str):
    # 1. Build Content HTML
    if not news_items:
        content_html = """
        <div class="empty-state">
          <p style="font-size: 16px; font-weight: 600; margin: 0 0 8px 0; color: #475569;">今日無最新新聞</p>
          <p style="margin: 0; font-size: 13px;">今日目前未監測到任何與關鍵字相關的新聞報導。</p>
        </div>
        """
    else:
        rows = []
        for item in news_items:
            # publish time formatting
            pub_time = item.publish_time.strftime("%H:%M") if hasattr(item.publish_time, 'strftime') else str(item.publish_time)
            rows.append(f"""
            <tr>
              <td>
                <div><a href="{item.url}" class="news-title" target="_blank">{item.title}</a></div>
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
        
        content_html = f"""
        <p style="font-size: 14px; color: #475569; margin: 0 0 16px 0;">
          今日共監測到 <strong>{len(news_items)}</strong> 則相關新聞報導，清單如下：
        </p>
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
    .empty-state {{
      text-align: center;
      padding: 40px 20px;
      background-color: #f1f5f9;
      border-radius: 8px;
      color: #64748b;
    }}
    .news-table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 16px;
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
    }}
    .badge-keyword {{
      background-color: #eff6ff;
      color: #1e40af;
      border: 1px solid #bfdbfe;
    }}
    .badge-source {{
      background-color: #f0fdf4;
      color: #166534;
      border: 1px solid #bbf7d0;
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
      <h1>國北教大新聞輿情監測日報</h1>
      <p>監測日期：{date_str}</p>
    </div>
    <div class="content">
      {content_html}
    </div>
    <div class="footer">
      本信件由國北教大新聞公佈欄系統自動發送。請勿直接回覆。
    </div>
  </div>
</body>
</html>"""

    # 2. Setup SMTP details
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"【國北教大輿情日報】{date_str} - 共 {len(news_items)} 則新聞"
    msg["From"] = f"國北教大新聞公佈欄 <{settings.SMTP_USERNAME}>"
    msg["To"] = settings.EMAIL_RECIPIENT

    # Plain text version fallback
    plain_text = f"國北教大新聞輿情監測日報 ({date_str})\n\n"
    if not news_items:
        plain_text += "今日無最新新聞。\n"
    else:
        plain_text += f"今日共監測到 {len(news_items)} 則相關新聞報導：\n\n"
        for item in news_items:
            plain_text += f"- [{item.source}] {item.title} ({item.url})\n"
    
    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        # Connect to SMTP
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
        server.starttls()  # Upgrade connection to secure encrypted TLS
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_USERNAME, settings.EMAIL_RECIPIENT, msg.as_string())
        server.quit()
        print("[Mailer] Daily news email sent successfully via SMTP!")
        return True
    except Exception as e:
        print(f"[Mailer] Failed to send daily news email via SMTP: {e}")
        return False
