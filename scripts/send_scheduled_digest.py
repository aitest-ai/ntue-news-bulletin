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

RISK_KEYWORDS = {
    "霸凌": 5, "性騷": 5, "性侵": 5, "自殺": 5, "死亡": 5, "火災": 5, "中毒": 5,
    "資安": 5, "個資": 5, "洩漏": 5, "詐騙": 5, "警察": 4, "調查": 4, "懲處": 4,
    "違法": 4, "違規": 4, "事故": 4, "受傷": 4, "危機": 4, "緊急": 4,
    "爭議": 3, "爆料": 3, "投訴": 3, "抱怨": 3, "不滿": 3, "抗議": 3,
    "澄清": 3, "道歉": 3, "黑箱": 3, "不公": 3, "歧視": 3, "偏見": 3,
    "問題": 2, "沒辦法": 2, "無法": 2, "負評": 2, "炎上": 3, "停課": 3,
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
    if source in {"Dcard", "PTT", "Threads"} and score:
        score += 1
    return score


def short_link(item, base_url):
    url = str(item.get("url") or "").strip()
    if not url:
        return ""
    sid = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{base_url}/r/{sid}"


def format_item(item, base_url, include_reason=False):
    source = str(item.get("source") or "").strip()
    title = str(item.get("title") or "（無標題）").strip()
    link = short_link(item, base_url)
    lines = [f"• [{source}] {title}"]
    if include_reason:
        matched = [k for k in RISK_KEYWORDS if k in title][:3]
        if matched:
            lines.append(f"  注意原因：標題含「{'、'.join(matched)}」等風險訊號")
        elif source in {"Dcard", "PTT", "Threads"}:
            lines.append("  注意原因：社群討論，建議持續觀察是否擴散")
    if link:
        lines.append(f"  查看原文：{link}")
    return "\n".join(lines)


def fallback_summary(selected, attention):
    if not selected:
        return "本期未取得足夠公開資料，建議確認資料來源狀態。"
    if not attention:
        return "本期監測以一般校園、活動與學習相關資訊為主，暫未偵測到明顯需要立即處理的風險訊號，建議維持例行監測。"
    high = sum(1 for x in attention if risk_score(x) >= 5)
    if high:
        return f"本期共有 {len(attention)} 則訊息建議優先檢視，其中 {high} 則具有較高風險訊號。建議先確認內容真實性、討論擴散程度與是否涉及校譽、學生安全或行政處置。"
    return f"本期共有 {len(attention)} 則訊息值得持續觀察，目前未見明確重大危機訊號；建議先確認原文脈絡與後續討論是否擴大。"


def ai_summary(selected, attention, days):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return fallback_summary(selected, attention)

    compact = [{
        "title": x.get("title"), "source": x.get("source"), "publish_time": x.get("publish_time"),
        "risk_score": risk_score(x),
    } for x in selected[:100]]
    prompt = (
        "你是國立臺北教育大學校級輿情分析助理。依公開新聞與社群標題，撰寫繁體中文主管摘要，120到180字。"
        "先說整體輿情，再說是否有需處理或需注意議題，最後給一句具體建議。不得杜撰；資料不足要明說。"
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
        text = "".join(p.get("text", "") for p in data.get("candidates", [{}])[0].get("content", {}).get("parts", []))
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

    ranked = sorted(selected, key=lambda x: (risk_score(x), str(x.get("publish_time") or "")), reverse=True)
    attention = [x for x in ranked if risk_score(x) >= 3][:5]
    attention_urls = {str(x.get("url") or "") for x in attention}
    other = [x for x in selected if str(x.get("url") or "") not in attention_urls][:5]

    high_count = sum(1 for x in attention if risk_score(x) >= 5)
    if high_count:
        level = "🔴 建議優先檢視"
        prefix = "【需注意】"
    elif attention:
        level = "🟡 持續觀察"
        prefix = "【觀察】"
    else:
        level = "🟢 例行監測"
        prefix = "【例行】"

    subject = f"{prefix}{settings.get('subject_prefix','【國北教大輿情快報】')}{now.strftime('%Y/%m/%d')} {slot}"
    summary = ai_summary(selected, attention, days)

    overview = (
        f"監測時間：{now.strftime('%Y/%m/%d %H:%M')}\n"
        f"統計期間：最近 {days} 天\n"
        f"整體燈號：{level}\n"
        f"總資料：{len(selected)}｜新聞：{news_count}｜社群：{social_count}\n"
        f"需注意：{len(attention)} 則｜高風險：{high_count} 則"
    )
    attention_text = "\n\n".join(format_item(x, base_url, True) for x in attention) if attention else "目前未偵測到明顯需要立即處理或特別注意的訊息。"
    other_text = "\n\n".join(format_item(x, base_url, False) for x in other) if other else "本期無其他最新資訊。"
    report_url = f"{base_url}/reports"
    return subject, overview, summary, attention_text, other_text, report_url, f"{base_url}/settings"


def submit_to_formsubmit(recipient, report):
    subject, overview, summary, attention_text, other_text, report_url, source_url = report
    endpoint = f"https://formsubmit.co/ajax/{urllib.parse.quote(recipient, safe='@.+-_')}"
    data = urllib.parse.urlencode({
        "_subject": subject,
        "_template": "box",
        "_captcha": "false",
        "_url": source_url,
        "主管快覽": overview,
        "AI 輿情摘要": summary,
        "需注意訊息": attention_text,
        "其他最新資訊": other_text,
        "完整 AI 輿情報告": report_url,
    }).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://ntue-news-bulletin.vercel.app",
            "Referer": source_url,
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
