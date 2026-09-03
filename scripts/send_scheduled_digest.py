#!/usr/bin/env python3
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "frontend" / "public" / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"
NEWS_FILE = DATA_DIR / "news.json"
STATE_FILE = DATA_DIR / "email-state.json"
TAIPEI = timezone(timedelta(hours=8))
SOCIAL = {"Dcard", "PTT", "Threads", "Instagram"}

# Strong signals are intentionally weighted higher. Generic wording such as
# 「問題」「無法」 alone should not make an item appear in an executive brief.
RISK_KEYWORDS = {
    "霸凌": 6, "性騷": 6, "性侵": 6, "自殺": 6, "死亡": 6, "火災": 6, "中毒": 6,
    "資安": 6, "個資": 6, "洩漏": 6, "詐騙": 6,
    "警察": 5, "調查": 5, "懲處": 5, "違法": 5, "違規": 5,
    "事故": 5, "受傷": 5, "危機": 5, "緊急": 5,
    "爭議": 4, "爆料": 4, "投訴": 4, "抱怨": 4, "不滿": 4,
    "抗議": 4, "澄清": 4, "道歉": 4, "黑箱": 4, "不公": 4,
    "歧視": 4, "偏見": 4, "炎上": 4, "停課": 4,
    "問題": 1, "沒辦法": 1, "無法": 1, "負評": 3,
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
    slots = []
    sent = state.setdefault("last_sent", {})
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


def select_items(feed, days):
    cutoff = datetime.now(TAIPEI) - timedelta(days=days)
    selected = []
    for item in feed.get("items", []):
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
    source = str(item.get("source") or "")
    score = sum(weight for keyword, weight in RISK_KEYWORDS.items() if keyword in title)
    # A risk-bearing social post is slightly more urgent because it can spread rapidly.
    if source in {"Dcard", "PTT", "Threads"} and score >= 3:
        score += 1
    return score


def short_link(item, base_url):
    url = str(item.get("url") or "").strip()
    if not url:
        return ""
    sid = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{base_url}/r/{sid}"


def attention_reason(item):
    title = str(item.get("title") or "")
    score = risk_score(item)
    matched = [k for k in RISK_KEYWORDS if RISK_KEYWORDS[k] >= 3 and k in title][:3]
    if score >= 7:
        level = "優先檢視"
    elif score >= 5:
        level = "需注意"
    else:
        level = "持續觀察"
    if matched:
        return f"{level}｜涉及「{'、'.join(matched)}」等風險訊號"
    return f"{level}｜社群或媒體內容建議確認脈絡與後續擴散"


def format_attention_item(item, base_url, index):
    source = str(item.get("source") or "").strip()
    title = str(item.get("title") or "（無標題）").strip()
    link = short_link(item, base_url)
    lines = [f"{index}. [{source}] {title}", f"   {attention_reason(item)}"]
    if link:
        lines.append(f"   查看原文：{link}")
    return "\n".join(lines)


def fallback_summary(selected, attention):
    if not selected:
        return "本期公開資料不足，建議確認資料來源是否正常。"
    if not attention:
        return "本期公開新聞與社群內容以一般校園、活動及學習資訊為主，未偵測到明顯需要立即處理的風險訊號。建議維持例行監測即可。"
    high = sum(1 for x in attention if risk_score(x) >= 7)
    if high:
        return f"本期有 {len(attention)} 則訊息值得檢視，其中 {high} 則具較高風險訊號。建議先確認原文真實性、討論擴散程度，以及是否涉及學生安全、校譽或行政處置。"
    return f"本期有 {len(attention)} 則訊息值得持續觀察，目前未見明確重大危機。建議確認原文脈絡，並留意同一議題是否跨平台增加或持續發酵。"


def ai_summary(selected, attention, days):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return fallback_summary(selected, attention)

    compact = [{
        "title": x.get("title"),
        "source": x.get("source"),
        "publish_time": x.get("publish_time"),
        "risk_score": risk_score(x),
    } for x in selected[:100]]
    prompt = (
        "你是國立臺北教育大學校級輿情分析助理。依公開新聞與社群標題，撰寫繁體中文主管摘要，120到180字。"
        "先說整體輿情，再說是否有需處理或需注意議題，最後給一句具體建議。"
        "不要逐則摘要、不要列流水帳、不得杜撰；資料不足要明說。"
        f"\n期間：最近 {days} 天\n資料：{json.dumps(compact, ensure_ascii=False)}"
    )
    payload = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 320},
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        data=payload,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = "".join(
            p.get("text", "")
            for p in data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        )
        return text.strip() or fallback_summary(selected, attention)
    except Exception as exc:
        print(f"[digest] Gemini summary fallback: {exc}")
        return fallback_summary(selected, attention)


def build_report(settings, feed, slot):
    days = int(settings.get("report_days", 7) or 7)
    selected = select_items(feed, days)
    news_count = sum(1 for x in selected if x.get("source") not in SOCIAL)
    social_count = sum(1 for x in selected if x.get("source") in SOCIAL)
    base_url = os.getenv("PUBLIC_BASE_URL", "https://ntue-news-bulletin.vercel.app").rstrip("/")
    now = datetime.now(TAIPEI)

    ranked = sorted(
        selected,
        key=lambda x: (risk_score(x), str(x.get("publish_time") or "")),
        reverse=True,
    )
    # Executive email is intentionally selective: only material items, maximum four.
    attention = [x for x in ranked if risk_score(x) >= 4][:4]

    high_count = sum(1 for x in attention if risk_score(x) >= 7)
    if high_count:
        level = "🔴 建議優先檢視"
        prefix = "【需注意】"
        action = "建議先確認高風險訊息原文與擴散程度，再判斷是否需由相關單位回應。"
    elif attention:
        level = "🟡 持續觀察"
        prefix = "【觀察】"
        action = "目前不需立即處置；建議持續觀察相關討論是否增加、跨平台擴散或出現媒體跟進。"
    else:
        level = "🟢 例行監測"
        prefix = "【例行】"
        action = "目前無需特別處理，維持例行監測即可。"

    subject = f"{prefix}{settings.get('subject_prefix','【國北教大輿情快報】')}{now.strftime('%Y/%m/%d')} {slot}"
    summary = ai_summary(selected, attention, days)

    overview = (
        f"監測時間：{now.strftime('%Y/%m/%d %H:%M')}\n"
        f"統計期間：最近 {days} 天\n"
        f"整體燈號：{level}\n"
        f"監測量：{len(selected)} 則（新聞 {news_count}｜社群 {social_count}）\n"
        f"需關注訊息：{len(attention)} 則"
    )

    attention_text = (
        "\n\n".join(
            format_attention_item(item, base_url, index)
            for index, item in enumerate(attention, start=1)
        )
        if attention
        else "本期未偵測到需要特別處理或持續追蹤的訊息。"
    )

    report_url = f"{base_url}/reports"
    return {
        "subject": subject,
        "overview": overview,
        "summary": summary,
        "action": action,
        "attention": attention_text,
        "report_url": report_url,
        "source_url": f"{base_url}/settings",
    }


def submit_to_formsubmit(recipient, report):
    endpoint = f"https://formsubmit.co/ajax/{urllib.parse.quote(recipient, safe='@.+-_')}"
    data = urllib.parse.urlencode({
        "_subject": report["subject"],
        "_template": "box",
        "_captcha": "false",
        "_url": report["source_url"],
        "主管快覽": report["overview"],
        "本期研判摘要": report["summary"],
        "建議處置": report["action"],
        "需關注原文": report["attention"],
        "完整 AI 輿情報告": report["report_url"],
    }).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://ntue-news-bulletin.vercel.app",
            "Referer": report["source_url"],
            "User-Agent": "Mozilla/5.0 NTUE-Opinion-Monitor/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            status = resp.status
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}
        success = str(payload.get("success", "")).lower() == "true"
        print(f"[digest] FormSubmit response HTTP {status} for {recipient}: {body[:500]}")
        if not success:
            print(f"[digest] FormSubmit rejected submission for {recipient}")
        return success
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        print(f"[digest] FormSubmit HTTP {exc.code} for {recipient}: {detail[:800]}")
        return False
    except Exception as exc:
        print(f"[digest] FormSubmit failed for {recipient}: {exc}")
        return False


def send_email(settings, feed, slot):
    recipients = [str(x).strip() for x in settings.get("recipients", []) if str(x).strip()]
    if not recipients:
        print("[digest] no recipients configured; cannot send email")
        return False
    report = build_report(settings, feed, slot)
    results = [submit_to_formsubmit(email, report) for email in recipients]
    success_count = sum(1 for ok in results if ok)
    print(f"[digest] FormSubmit accepted {success_count}/{len(recipients)} recipient submission(s) for slot {slot}")
    return success_count == len(recipients)


def main():
    settings = load_json(SETTINGS_FILE, {})
    state = load_json(STATE_FILE, {"last_sent": {}})
    feed = load_json(NEWS_FILE, {"items": []})
    now = datetime.now(TAIPEI)
    slots = due_slots(settings, state, now)
    if not slots:
        print("[digest] no scheduled email due")
        return
    for slot, key in slots:
        if send_email(settings, feed, slot):
            state.setdefault("last_sent", {})[slot] = key
            save_json(STATE_FILE, state)


if __name__ == "__main__":
    main()
