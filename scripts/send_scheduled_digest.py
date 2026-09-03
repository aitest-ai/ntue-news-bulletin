#!/usr/bin/env python3
import html
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "frontend" / "public" / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"
NEWS_FILE = DATA_DIR / "news.json"
STATE_FILE = DATA_DIR / "email-state.json"
TAIPEI = timezone(timedelta(hours=8))
SOCIAL = {"Dcard", "PTT", "Threads", "Instagram"}
NTUE_TERMS = [
    "國立臺北教育大學", "國立台北教育大學", "臺北教育大學", "台北教育大學",
    "國北教大", "國北教", "北教大", "ntue", "national taipei university of education",
]
RISK_KEYWORDS = {
    "霸凌": 6, "性騷": 6, "性侵": 6, "自殺": 6, "死亡": 6, "火災": 6, "中毒": 6,
    "資安": 6, "個資": 6, "洩漏": 6, "詐騙": 6,
    "警察": 5, "調查": 5, "懲處": 5, "違法": 5, "違規": 5,
    "事故": 5, "受傷": 5, "危機": 5, "緊急": 5,
    "爭議": 4, "爆料": 4, "投訴": 4, "抱怨": 4, "不滿": 4,
    "抗議": 4, "澄清": 4, "道歉": 4, "黑箱": 4, "不公": 4,
    "歧視": 4, "偏見": 4, "炎上": 4, "停課": 4, "負評": 3,
}


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def due_slots(settings, state, now):
    if not settings.get("email_enabled"):
        return []
    sent = state.setdefault("last_sent", {})
    slots = []
    for slot in settings.get("schedules", []):
        try:
            hh, mm = map(int, slot.split(":"))
            target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        except Exception:
            continue
        key = f"{now.date().isoformat()}@{slot}"
        delta = (now - target).total_seconds() / 60
        if 0 <= delta <= 60 and sent.get(slot) != key:
            slots.append((slot, key))
    return slots


def normalize(value):
    return " ".join(str(value or "").replace("臺", "台").lower().split())


def is_ntue_relevant(item):
    title = normalize(item.get("title"))
    source = normalize(item.get("source"))
    publisher = normalize(item.get("publisher"))
    url = str(item.get("url") or "")
    host = (urlparse(url).netloc or "").lower()
    haystack = f"{title} {source} {publisher}"
    if any(normalize(term) in haystack for term in NTUE_TERMS):
        return True
    if host.endswith("ntue.edu.tw"):
        return True
    if item.get("source") == "Dcard" and "/f/ntue" in url.lower():
        return True
    return False


def select_items(feed, days):
    cutoff = datetime.now(TAIPEI) - timedelta(days=days)
    selected = []
    for item in feed.get("items", []):
        if not is_ntue_relevant(item):
            continue
        raw = item.get("publish_time")
        if not raw:
            selected.append(item)
            continue
        try:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TAIPEI)
            if dt >= cutoff:
                selected.append(item)
        except Exception:
            selected.append(item)
    return selected


def risk_score(item):
    title = str(item.get("title") or "")
    score = sum(weight for keyword, weight in RISK_KEYWORDS.items() if keyword in title)
    if item.get("source") in {"Dcard", "PTT", "Threads"} and score >= 3:
        score += 1
    return score


def resolve_original_url(url):
    url = str(url or "").strip()
    if not url:
        return ""
    host = (urlparse(url).netloc or "").lower()
    if host not in {"news.google.com", "www.news.google.com"}:
        return url
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "zh-TW,zh;q=0.9"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            final_url = resp.geturl()
        final_host = (urlparse(final_url).netloc or "").lower()
        if final_host and "google." not in final_host:
            return final_url
    except Exception:
        pass
    return ""


def attention_reason(item):
    title = str(item.get("title") or "")
    matched = [k for k, weight in RISK_KEYWORDS.items() if weight >= 3 and k in title][:3]
    score = risk_score(item)
    level = "優先檢視" if score >= 7 else "需注意" if score >= 5 else "持續觀察"
    return f"{level}：涉及「{'、'.join(matched)}」等風險訊號" if matched else f"{level}：建議確認內容脈絡與後續擴散"


def fallback_report(selected, attention, days):
    if not selected:
        return {
            "overall": "本期未取得足夠且可確認與國北教大相關的公開資料。",
            "immediate_action": "目前無需特別處理，建議確認資料來源是否正常。",
            "themes": ["本期有效資料不足"],
            "risk_assessment": "未偵測到可確認的重大風險訊號。",
            "recommendations": ["維持例行監測"],
            "watchlist": [],
        }
    if not attention:
        return {
            "overall": f"最近 {days} 天與國北教大明確相關的公開新聞與社群內容以一般校園、活動及學習資訊為主。",
            "immediate_action": "本期無需特別處理，維持例行監測即可。",
            "themes": ["一般校園資訊", "活動與學習資訊"],
            "risk_assessment": "目前未偵測到明顯需要立即處理的風險訊號。",
            "recommendations": ["維持例行監測", "留意同一議題是否跨平台快速增加"],
            "watchlist": [],
        }
    return {
        "overall": f"本期有 {len(attention)} 則與國北教大明確相關的訊息值得進一步檢視。",
        "immediate_action": "先確認原文脈絡、真實性與擴散程度，再判斷是否需要行政回應。",
        "themes": ["需關注公開討論"],
        "risk_assessment": "目前偵測到少數風險訊號，但僅憑標題不足以認定事件嚴重程度。",
        "recommendations": ["確認原文", "觀察跨平台擴散", "必要時轉交相關單位"],
        "watchlist": [],
    }


def generate_ai_report(selected, attention, days):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("[digest] GEMINI_API_KEY missing; using deterministic report fallback")
        return fallback_report(selected, attention, days), False
    compact = [{
        "title": item.get("title"), "source": item.get("source"), "publisher": item.get("publisher"),
        "publish_time": item.get("publish_time"), "risk_score": risk_score(item),
    } for item in selected[:120]]
    prompt = (
        "你是國立臺北教育大學校級輿情分析助理。請依已通過國北教大相關性篩選的公開新聞與社群標題，"
        "產生主管用繁體中文輿情報告。不得因單一負面字詞就推論危機；沒有需要注意的事件就明確寫『本期無需特別關注』；"
        "不得杜撰。只回傳 JSON，格式為："
        '{"overall":"150-250字整體摘要","immediate_action":"是否需要立即處理及具體建議",'
        '"themes":["主要議題"],"risk_assessment":"整體風險研判","recommendations":["建議"],"watchlist":["持續觀察議題"]}'
        f"\n期間：最近 {days} 天\n資料：{json.dumps(compact, ensure_ascii=False)}"
    )
    payload = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.15, "responseMimeType": "application/json", "maxOutputTokens": 1200},
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        data=payload,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=50) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = "".join(p.get("text", "") for p in data.get("candidates", [{}])[0].get("content", {}).get("parts", [])).strip()
        result = json.loads(text)
        required = ["overall", "immediate_action", "themes", "risk_assessment", "recommendations", "watchlist"]
        if not all(key in result for key in required):
            raise ValueError("incomplete Gemini schema")
        return result, True
    except Exception as exc:
        print(f"[digest] Gemini full report fallback: {exc}")
        return fallback_report(selected, attention, days), False


def create_pdf(path, report, meta, attention, ai_generated):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    try:
        pdfmetrics.registerFont(UnicodeCIDFont("MSung-Light"))
        font = "MSung-Light"
    except Exception:
        font = "Helvetica"
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleTC", parent=styles["Title"], fontName=font, fontSize=19, leading=26, alignment=TA_CENTER, textColor=colors.HexColor("#17365D"), spaceAfter=8)
    h_style = ParagraphStyle("HeadingTC", parent=styles["Heading2"], fontName=font, fontSize=13, leading=19, textColor=colors.HexColor("#17365D"), spaceBefore=8, spaceAfter=5)
    body_style = ParagraphStyle("BodyTC", parent=styles["BodyText"], fontName=font, fontSize=10.5, leading=17, textColor=colors.HexColor("#222222"), spaceAfter=5)
    small_style = ParagraphStyle("SmallTC", parent=body_style, fontSize=9, leading=14, textColor=colors.HexColor("#666666"))
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=18*mm, leftMargin=18*mm, topMargin=16*mm, bottomMargin=16*mm, title=f"國立臺北教育大學 輿情報告 {meta['date']}", author="NTUE Opinion Monitor")
    story = [
        Paragraph("國立臺北教育大學 輿情報告", title_style),
        Paragraph(f"{meta['date']} {meta['slot']}｜最近 {meta['days']} 天｜{'AI 生成' if ai_generated else '規則備援'}", small_style),
        Spacer(1, 5*mm),
    ]
    table = Table([["監測資料", str(meta["total"])], ["新聞", str(meta["news_count"])], ["社群", str(meta["social_count"])], ["需關注", str(len(attention))]], colWidths=[45*mm, 35*mm], hAlign="LEFT")
    table.setStyle(TableStyle([("FONTNAME", (0,0), (-1,-1), font), ("FONTSIZE", (0,0), (-1,-1), 9.5), ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#EEF3F8")), ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#C8D1DC")), ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5)]))
    story += [table, Spacer(1, 5*mm)]

    def section(title, text):
        story.append(Paragraph(title, h_style))
        story.append(Paragraph(html.escape(str(text)).replace("\n", "<br/>"), body_style))

    section("一、整體輿情摘要", report.get("overall", ""))
    section("二、是否需要立即處理", report.get("immediate_action", ""))
    story.append(Paragraph("三、主要議題", h_style))
    for theme in report.get("themes") or ["本期無明顯集中議題。"]:
        story.append(Paragraph(f"• {html.escape(str(theme))}", body_style))
    section("四、整體風險研判", report.get("risk_assessment", ""))
    story.append(Paragraph("五、建議處置", h_style))
    for rec in report.get("recommendations") or ["維持例行監測。"]:
        story.append(Paragraph(f"• {html.escape(str(rec))}", body_style))
    story.append(Paragraph("六、需關注原文", h_style))
    if not attention:
        story.append(Paragraph("本期無需特別關注訊息。", body_style))
    else:
        for index, item in enumerate(attention, start=1):
            story.append(Paragraph(f"{index}. [{html.escape(str(item.get('source') or ''))}] {html.escape(str(item.get('title') or '（無標題）'))}", body_style))
            story.append(Paragraph(html.escape(attention_reason(item)), small_style))
            original = resolve_original_url(item.get("url"))
            if original:
                story.append(Paragraph(f'<link href="{html.escape(original, quote=True)}">查看原始來源</link>', small_style))
            else:
                story.append(Paragraph("原始發布網址暫無法可靠解析，因此不提供 Google News 中繼網址。", small_style))
            story.append(Spacer(1, 2*mm))
    story.append(Paragraph("七、持續觀察項目", h_style))
    watchlist = report.get("watchlist") or []
    if watchlist:
        for item in watchlist:
            story.append(Paragraph(f"• {html.escape(str(item))}", body_style))
    else:
        story.append(Paragraph("本期無額外持續觀察項目。", body_style))
    story += [Spacer(1, 6*mm), Paragraph("本報告由公開新聞與社群監測資料自動整理，供校務輿情初步判讀使用；重要事件仍應回到原始來源確認。", small_style)]
    doc.build(story)


def encode_multipart(fields, file_field, file_path):
    boundary = "----NTUEFormBoundary" + uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        chunks += [f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(), str(value).encode("utf-8"), b"\r\n"]
    filename = Path(file_path).name
    chunks += [
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode(),
        b"Content-Type: application/pdf\r\n\r\n",
        Path(file_path).read_bytes(), b"\r\n", f"--{boundary}--\r\n".encode(),
    ]
    return boundary, b"".join(chunks)


def submit_to_formsubmit(recipient, subject, body_fields, source_url, pdf_path):
    # File uploads are documented on the normal FormSubmit endpoint, not /ajax/.
    endpoint = f"https://formsubmit.co/{urllib.parse.quote(recipient, safe='@.+-_')}"
    fields = {
        "_subject": subject,
        "_template": "box",
        "_captcha": "false",
        "_url": source_url,
        **body_fields,
    }
    boundary, data = encode_multipart(fields, "attachment", pdf_path)
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Origin": "https://ntue-news-bulletin.vercel.app",
            "Referer": source_url,
            "User-Agent": "Mozilla/5.0 NTUE-Opinion-Monitor/3.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            response_body = resp.read().decode("utf-8", errors="ignore")
            status = resp.status
        lower = response_body.lower()
        success = 200 <= status < 400 and "unable to submit" not in lower and "error" not in lower
        print(f"[digest] FormSubmit file-upload HTTP {status} for {recipient}; attachment={Path(pdf_path).stat().st_size}B")
        return success
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        print(f"[digest] FormSubmit HTTP {exc.code} for {recipient}: {detail[:800]}")
        return False
    except Exception as exc:
        print(f"[digest] FormSubmit failed for {recipient}: {exc}")
        return False


def build_and_send(settings, feed, slot):
    days = int(settings.get("report_days", 7) or 7)
    selected = select_items(feed, days)
    ranked = sorted(selected, key=lambda x: (risk_score(x), str(x.get("publish_time") or "")), reverse=True)
    attention = [item for item in ranked if risk_score(item) >= 4][:5]
    report, ai_generated = generate_ai_report(selected, attention, days)
    news_count = sum(1 for item in selected if item.get("source") not in SOCIAL)
    social_count = sum(1 for item in selected if item.get("source") in SOCIAL)
    now = datetime.now(TAIPEI)
    base_url = os.getenv("PUBLIC_BASE_URL", "https://ntue-news-bulletin.vercel.app").rstrip("/")
    prefix = "【需注意】" if any(risk_score(item) >= 7 for item in attention) else "【觀察】" if attention else "【例行】"
    subject = f"{prefix}{settings.get('subject_prefix','【國北教大輿情快報】')}{now.strftime('%Y/%m/%d')} {slot}"
    meta = {"date": now.strftime("%Y/%m/%d"), "slot": slot, "days": days, "total": len(selected), "news_count": news_count, "social_count": social_count}
    pdf_path = Path("/tmp") / f"NTUE_Opinion_Report_{now.strftime('%Y%m%d')}_{slot.replace(':','')}.pdf"
    create_pdf(pdf_path, report, meta, attention, ai_generated)
    if pdf_path.stat().st_size > 9_500_000:
        print(f"[digest] PDF too large for FormSubmit: {pdf_path.stat().st_size} bytes")
        return False
    attention_text = "\n".join(f"• [{item.get('source','')}] {item.get('title','')} — {attention_reason(item)}" for item in attention) if attention else "本期無需特別關注訊息。"
    body_fields = {
        "主管快覽": f"監測時間：{now.strftime('%Y/%m/%d %H:%M')}\n統計期間：最近 {days} 天\n有效相關資料：{len(selected)} 則（新聞 {news_count}｜社群 {social_count}）\n需關注訊息：{len(attention)} 則",
        "本期研判摘要": report.get("overall", ""),
        "建議處置": report.get("immediate_action", ""),
        "需關注訊息": attention_text,
        "附件": "完整輿情報告請見本信 PDF 附件。",
        "系統報告頁": f"{base_url}/reports",
    }
    recipients = [str(x).strip() for x in settings.get("recipients", []) if str(x).strip()]
    if not recipients:
        print("[digest] no recipients configured")
        return False
    source_url = f"{base_url}/settings"
    results = [submit_to_formsubmit(recipient, subject, body_fields, source_url, pdf_path) for recipient in recipients]
    success_count = sum(1 for ok in results if ok)
    print(f"[digest] FormSubmit accepted {success_count}/{len(recipients)}; relevant={len(selected)} attention={len(attention)} ai_generated={ai_generated} pdf={pdf_path.stat().st_size}B")
    return success_count == len(recipients)


def main():
    settings = load_json(SETTINGS_FILE, {})
    state = load_json(STATE_FILE, {"last_sent": {}})
    feed = load_json(NEWS_FILE, {"items": []})
    now = datetime.now(TAIPEI)
    slots = due_slots(settings, state, now)
    if "--is-due" in sys.argv:
        raise SystemExit(0 if slots else 1)
    if not slots:
        print("[digest] no scheduled email due")
        return
    for slot, key in slots:
        if build_and_send(settings, feed, slot):
            state.setdefault("last_sent", {})[slot] = key
            save_json(STATE_FILE, state)


if __name__ == "__main__":
    main()
