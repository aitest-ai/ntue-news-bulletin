#!/usr/bin/env python3
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
        if 0 <= delta <= 25 and sent.get(slot) != key:
            slots.append((slot, key))
    return slots


def ai_summary(items, days):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return "本期輿情資料已更新，請登入系統查看完整 AI 輿情報告。"

    compact = [
        {"title": x.get("title"), "source": x.get("source"), "publish_time": x.get("publish_time")}
        for x in items[:100]
    ]
    prompt = (
        "你是國立臺北教育大學校級輿情分析助理。請依提供的公開新聞與社群標題，"
        "用繁體中文撰寫一段 180 字以內的主管摘要，包含主要議題、是否有明顯風險與建議是否持續觀察。"
        "不得杜撰，資料不足要明說。\n"
        f"期間：最近 {days} 天；資料：{json.dumps(compact, ensure_ascii=False)}"
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
        return "".join(
            p.get("text", "")
            for p in data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        ).strip() or "本期資料已更新。"
    except Exception as exc:
        print(f"[digest] Gemini summary fallback: {exc}")
        return "本期輿情資料已更新，請登入系統查看完整 AI 輿情報告。"


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


def build_message(settings, feed, slot):
    days = int(settings.get("report_days", 1) or 1)
    selected = select_items(feed, days)
    news_count = sum(1 for x in selected if x.get("source") not in SOCIAL)
    social_count = sum(1 for x in selected if x.get("source") in SOCIAL)
    latest_n = int(settings.get("include_latest_items", 20) or 20)
    latest = selected[:latest_n]
    summary = ai_summary(selected, days)
    base_url = os.getenv("PUBLIC_BASE_URL", "https://ntue-news-bulletin.vercel.app").rstrip("/")
    now = datetime.now(TAIPEI)
    subject = f"{settings.get('subject_prefix','【國北教大輿情快報】')}{now.strftime('%Y/%m/%d')} {slot}"

    lines = [
        "國立臺北教育大學 輿情快報",
        f"產生時間：{now.strftime('%Y/%m/%d %H:%M')}",
        f"統計期間：最近 {days} 天",
        "",
        f"總資料：{len(selected)}｜新聞：{news_count}｜社群：{social_count}",
        "",
        "【AI 摘要】",
        summary,
        "",
        "【最新訊息】",
    ]
    for item in latest:
        title = str(item.get("title") or "（無標題）").strip()
        source = str(item.get("source") or "").strip()
        url = str(item.get("url") or "").strip()
        lines.append(f"• [{source}] {title}")
        if url:
            lines.append(f"  {url}")
    lines.extend(["", f"完整輿情報告：{base_url}/reports"])
    return subject, "\n".join(lines)


def submit_to_formsubmit(recipient, subject, message):
    endpoint = f"https://formsubmit.co/ajax/{urllib.parse.quote(recipient, safe='@.+-_')}"
    data = urllib.parse.urlencode({
        "_subject": subject,
        "_template": "table",
        "_captcha": "false",
        "系統": "國立臺北教育大學輿情監測系統",
        "報告內容": message,
    }).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": "NTUE-Opinion-Monitor/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            status = resp.status
        print(f"[digest] FormSubmit response HTTP {status} for {recipient}: {body[:400]}")
        return 200 <= status < 300
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

    subject, message = build_message(settings, feed, slot)
    results = [submit_to_formsubmit(email, subject, message) for email in recipients]
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
