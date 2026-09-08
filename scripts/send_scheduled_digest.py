#!/usr/bin/env python3
"""Lightweight scheduled NTUE opinion bulletin sender.

The email is a collection brief rather than an administrative decision report:
- only items with a verifiable timestamp in the previous 24 hours;
- concise AI-assisted summary with deterministic fallback;
- deliberately non-departmental suggestion;
- source links in the email body;
- no PDF attachment.

AI failure must never block email delivery.
"""
import html
import json
import os
import sys
import time
import urllib.error
import urllib.request
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
    """Legacy direct-run support; profile delivery uses send_delivery_profiles.py."""
    if not settings.get("email_enabled"):
        return []
    sent = state.setdefault("last_sent", {})
    slots = []
    for slot in settings.get("schedules", []):
        try:
            hh, mm = map(int, str(slot).split(":"))
            target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        except Exception:
            continue
        key = f"{now.date().isoformat()}@{slot}"
        if now >= target and sent.get(slot) != key:
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


def _parse_publish_time(raw):
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TAIPEI)
        return dt.astimezone(TAIPEI)
    except Exception:
        return None


def select_items(feed, hours=24):
    """Strict rolling window. Undated/unparseable items are excluded from email."""
    now = datetime.now(TAIPEI)
    cutoff = now - timedelta(hours=hours)
    selected = []
    for item in feed.get("items", []):
        if not isinstance(item, dict) or not is_ntue_relevant(item):
            continue
        dt = _parse_publish_time(item.get("publish_time"))
        if dt is None:
            continue
        if cutoff <= dt <= now + timedelta(minutes=10):
            selected.append(dict(item))
    return selected


def risk_score(item):
    title = str(item.get("title") or "")
    score = sum(weight for keyword, weight in RISK_KEYWORDS.items() if keyword in title)
    if item.get("source") in {"Dcard", "PTT", "Threads"} and score >= 3:
        score += 1
    return score


def safe_suggestion(selected):
    """Never names a responsible office, department, or person."""
    if not selected:
        return "目前沒有新增相關公開訊息；維持例行監測即可。"
    if any(risk_score(item) >= 7 for item in selected):
        return "建議先閱讀相關原文並確認內容、時間與擴散情形；如後續資訊增加，再依校內既有流程研議是否需要進一步處理。"
    if any(risk_score(item) >= 4 for item in selected):
        return "建議先查看相關原文、確認事件脈絡，並持續觀察後續是否出現更多討論；本快報僅提供輿情蒐集與初步整理。"
    return "目前以掌握公開訊息與持續觀察即可；如需進一步判讀，可再查閱原文或使用 AI 協助整理。"


def fallback_summary(selected):
    if not selected:
        return "過去 24 小時內，系統未蒐集到可確認發布時間且與國立臺北教育大學明確相關的新增公開新聞或社群訊息。"
    news_count = sum(1 for item in selected if item.get("source") not in SOCIAL)
    social_count = len(selected) - news_count
    titles = [str(item.get("title") or "").strip() for item in selected if str(item.get("title") or "").strip()][:4]
    title_text = "、".join(f"「{title}」" for title in titles)
    summary = f"過去 24 小時共蒐集到 {len(selected)} 則與國北教大明確相關的公開訊息，其中新聞 {news_count} 則、社群 {social_count} 則。"
    if title_text:
        summary += f"目前主要內容包括{title_text}。"
    summary += "本快報僅依公開來源整理近期動態，不據此推定事件責任、嚴重程度或應由特定單位處理。"
    return summary


def _workflow_headers():
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-github-run-id": os.getenv("GITHUB_RUN_ID", "").strip(),
        "x-github-sha": os.getenv("GITHUB_SHA", "").strip(),
        "x-github-workflow-token": os.getenv("GITHUB_WORKFLOW_TOKEN", "").strip(),
        "User-Agent": "NTUE-GitHub-Actions-Email-Brief/8.0",
    }


def generate_ai_summary(selected):
    """Use verified Vercel AI when available; fallback without blocking email."""
    if not selected:
        return fallback_summary(selected), False

    base_url = os.getenv("PUBLIC_BASE_URL", "https://ntue-news-bulletin.vercel.app").rstrip("/")
    if not os.getenv("GITHUB_RUN_ID", "").strip() or not os.getenv("GITHUB_SHA", "").strip() or not os.getenv("GITHUB_WORKFLOW_TOKEN", "").strip():
        print("[digest] workflow auth unavailable; using deterministic summary")
        return fallback_summary(selected), False

    items = [{
        "title": item.get("title"),
        "source": item.get("source"),
        "publisher": item.get("publisher"),
        "publish_time": item.get("publish_time"),
        "risk_score": risk_score(item),
    } for item in selected[:120]]
    payload = json.dumps({"days": 1, "items": items, "email_brief": True}, ensure_ascii=False).encode("utf-8")
    endpoint = f"{base_url}/api/ai-report/scheduled"
    last_error = None

    for attempt in range(1, 5):
        try:
            req = urllib.request.Request(endpoint, data=payload, headers=_workflow_headers(), method="POST")
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            report = data.get("report") if isinstance(data, dict) else None
            if isinstance(report, dict):
                summary = str(report.get("summary") or report.get("overall") or "").strip()
                if summary:
                    print(f"[digest] AI summary generated via scheduled endpoint; attempt={attempt}")
                    return summary, True
            last_error = "scheduled endpoint returned no summary"
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            last_error = f"HTTP {exc.code}: {detail[:300]}"
        except Exception as exc:
            last_error = str(exc)
        if attempt < 4:
            time.sleep(8)

    print(f"[digest] AI summary unavailable; using deterministic fallback: {last_error}")
    return fallback_summary(selected), False


def source_link(item):
    """Return only direct non-Google-news links already present in collected data."""
    for key in ("original_url", "source_url", "url"):
        url = str(item.get(key) or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        host = (urlparse(url).netloc or "").lower()
        if host in {"news.google.com", "www.news.google.com"}:
            continue
        return url
    return ""


def _format_item_time(item):
    dt = _parse_publish_time(item.get("publish_time"))
    return dt.strftime("%m/%d %H:%M") if dt else "時間未確認"


def build_email(summary, suggestion, selected, slot, include_latest_items):
    now = datetime.now(TAIPEI)
    selected = sorted(
        selected,
        key=lambda item: _parse_publish_time(item.get("publish_time")) or datetime.min.replace(tzinfo=TAIPEI),
        reverse=True,
    )
    display_items = selected[:max(1, min(int(include_latest_items or 20), 100))]
    news_count = sum(1 for item in selected if item.get("source") not in SOCIAL)
    social_count = len(selected) - news_count

    item_html = []
    item_text = []
    for index, item in enumerate(display_items, start=1):
        title = str(item.get("title") or "（無標題）").strip()
        source = str(item.get("source") or "公開來源").strip()
        publisher = str(item.get("publisher") or "").strip()
        meta = "｜".join(value for value in [source, publisher, _format_item_time(item)] if value)
        link = source_link(item)
        link_html = (
            f'<a href="{html.escape(link, quote=True)}" style="color:#0b5cab;text-decoration:underline;font-weight:700">查看來源連結</a>'
            if link else '<span style="color:#7a8494">來源網址目前無法可靠解析</span>'
        )
        item_html.append(
            '<div style="padding:13px 0;border-bottom:1px solid #e5e9ef">'
            f'<div style="font-weight:700;color:#172033;margin-bottom:4px">{index}. {html.escape(title)}</div>'
            f'<div style="font-size:12px;color:#6b7280;margin-bottom:5px">{html.escape(meta)}</div>'
            f'<div style="font-size:13px">{link_html}</div>'
            '</div>'
        )
        item_text.append(f"{index}. {title}\n   {meta}\n   {link or '來源網址目前無法可靠解析'}")

    if not item_html:
        item_html.append('<div style="color:#6b7280;padding:8px 0">過去 24 小時沒有符合條件的新增相關訊息。</div>')
        item_text.append("過去 24 小時沒有符合條件的新增相關訊息。")

    rows = [
        ("主管快覽",
         f"監測時間：{now.strftime('%Y/%m/%d %H:%M')}<br>"
         f"排程時段：{html.escape(slot)}<br>"
         "統計期間：過去 24 小時<br>"
         f"有效相關資料：{len(selected)} 則（新聞 {news_count}｜社群 {social_count}）"),
        ("本期研判摘要", html.escape(summary).replace("\n", "<br>")),
        ("簡單建議", html.escape(suggestion).replace("\n", "<br>")),
        ("相關訊息", "".join(item_html)),
    ]
    row_html = "".join(
        '<tr>'
        f'<td style="width:170px;background:#f1f4f7;padding:15px 16px;vertical-align:top;font-weight:800;color:#1f2937;border-bottom:1px solid #dfe5ec">{label}</td>'
        f'<td style="padding:15px 16px;vertical-align:top;color:#2b3340;border-bottom:1px solid #dfe5ec">{value}</td>'
        '</tr>'
        for label, value in rows
    )
    html_content = (
        '<div style="font-family:Arial,\'Noto Sans TC\',sans-serif;color:#222;line-height:1.7;background:#fff">'
        '<div style="max-width:880px;margin:0 auto;padding:18px 10px">'
        '<h2 style="color:#17365d;margin:0 0 22px;font-size:24px">國立臺北教育大學輿情快報</h2>'
        '<table role="presentation" style="border-collapse:collapse;width:100%;border:1px solid #dfe5ec">'
        f'{row_html}</table>'
        '<p style="font-size:12px;color:#7a8494;margin-top:14px">'
        '本快報由公開新聞與社群資料自動蒐集與摘要，目的為協助掌握輿情；重要內容仍請以原始來源為準。'
        '</p></div></div>'
    )
    text_content = (
        "國立臺北教育大學輿情快報\n\n"
        f"監測時間：{now.strftime('%Y/%m/%d %H:%M')}\n"
        f"排程時段：{slot}\n"
        "統計期間：過去 24 小時\n"
        f"有效相關資料：{len(selected)} 則（新聞 {news_count}｜社群 {social_count}）\n\n"
        f"本期研判摘要\n{summary}\n\n"
        f"簡單建議\n{suggestion}\n\n"
        "相關訊息\n" + "\n\n".join(item_text) +
        "\n\n本快報僅供輿情蒐集與初步整理；重要內容請回到原始來源確認。"
    )
    return html_content, text_content


def submit_via_brevo(recipient, subject, html_content, text_content):
    api_key = os.getenv("BREVO_API_KEY", "").strip()
    sender_email = os.getenv("BREVO_SENDER_EMAIL", "").strip()
    sender_name = os.getenv("BREVO_SENDER_NAME", "國北教大輿情監測").strip() or "國北教大輿情監測"
    if not api_key or not sender_email:
        print("[digest] Brevo sender configuration missing")
        return False

    payload = json.dumps({
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": recipient}],
        "subject": subject,
        "htmlContent": html_content,
        "textContent": text_content,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=payload,
        headers={
            "api-key": api_key,
            "accept": "application/json",
            "content-type": "application/json",
            "User-Agent": "NTUE-Opinion-Monitor/8.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            status = resp.status
        data = json.loads(body) if body else {}
        message_id = data.get("messageId")
        success = 200 <= status < 300 and bool(message_id)
        print(f"[digest] Brevo HTTP {status}; messageId={message_id or 'missing'}; html-only=true")
        return success
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        print(f"[digest] Brevo HTTP {exc.code}: {detail[:800]}")
        return False
    except Exception as exc:
        print(f"[digest] Brevo send failed: {exc}")
        return False


def build_and_send(settings, feed, slot):
    selected = select_items(feed, hours=24)
    selected = sorted(
        selected,
        key=lambda item: _parse_publish_time(item.get("publish_time")) or datetime.min.replace(tzinfo=TAIPEI),
        reverse=True,
    )
    summary, ai_generated = generate_ai_summary(selected)
    suggestion = safe_suggestion(selected)
    now = datetime.now(TAIPEI)
    subject_prefix = str(settings.get("subject_prefix") or "【國北教大輿情快報】").strip()
    subject = f"{subject_prefix}{now.strftime('%Y/%m/%d')} {slot}｜24小時"
    html_content, text_content = build_email(
        summary,
        suggestion,
        selected,
        slot,
        settings.get("include_latest_items", 20),
    )
    recipients = [str(value).strip() for value in settings.get("recipients", []) if str(value).strip()]
    if not recipients:
        print("[digest] no recipients configured")
        return False

    results = [submit_via_brevo(recipient, subject, html_content, text_content) for recipient in recipients]
    success_count = sum(1 for ok in results if ok)
    print(
        f"[digest] Brevo accepted {success_count}/{len(recipients)}; "
        f"window=24h relevant={len(selected)} ai_generated={ai_generated} attachment=none"
    )
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
