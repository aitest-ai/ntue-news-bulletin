#!/usr/bin/env python3
"""HTML-only NTUE bulletin that mirrors the dashboard's news/social feed cards."""
from __future__ import annotations

import html
import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from urllib.parse import urlparse

import send_scheduled_digest as legacy

TAIPEI = legacy.TAIPEI
SOCIAL = legacy.SOCIAL


def _is_google_news(url):
    host = (urlparse(str(url or "")).netloc or "").lower()
    return host in {"news.google.com", "www.news.google.com"}


def best_link(item):
    """Always return a clickable route; prefer a verified original URL."""
    for key in ("original_url", "source_url"):
        url = str(item.get(key) or "").strip()
        if url.startswith(("http://", "https://")) and not _is_google_news(url):
            return url, True
    url = str(item.get("url") or "").strip()
    if url.startswith(("http://", "https://")):
        return url, not _is_google_news(url)
    fallback = str(item.get("google_news_url") or "").strip()
    if fallback.startswith(("http://", "https://")):
        return fallback, False
    return "", False


def _fmt_time(item):
    dt = legacy._parse_publish_time(item.get("publish_time"))
    return dt.strftime("%m/%d %H:%M") if dt else "時間未確認"


def _card(item, social=False):
    title = str(item.get("title") or "（無標題）").strip()
    source = str(item.get("source") or "公開來源").strip()
    publisher = str(item.get("publisher") or "").strip()
    meta_parts = []
    if publisher and publisher != source:
        meta_parts.append(publisher)
    meta_parts.append(_fmt_time(item))
    meta = " · ".join(meta_parts)
    link, direct = best_link(item)

    pill_bg = "#fff3e6" if social else "#edf3ff"
    pill_fg = "#7a3e00" if social else "#315caa"
    if link:
        title_html = (
            f'<a href="{html.escape(link, quote=True)}" '
            'style="color:#14213d;text-decoration:none;font-weight:700;line-height:1.55">'
            f'{html.escape(title)}</a>'
        )
        cta = (
            f'<a href="{html.escape(link, quote=True)}" '
            'style="display:inline-block;margin-top:7px;color:#0b5cab;text-decoration:none;font-size:12px;font-weight:700">'
            + ("查看原文 →" if direct else "開啟來源 →") + "</a>"
        )
    else:
        title_html = f'<span style="font-weight:700;color:#14213d;line-height:1.55">{html.escape(title)}</span>'
        cta = ""

    return (
        '<div style="display:flex;gap:11px;padding:14px 0;border-bottom:1px solid #edf0f4">'
        f'<div style="flex:0 0 auto;align-self:flex-start;min-width:72px;text-align:center;font-size:11.5px;'
        f'font-weight:800;padding:6px 8px;border-radius:999px;color:{pill_fg};background:{pill_bg}">{html.escape(source)}</div>'
        '<div style="min-width:0;flex:1">'
        f'<div>{title_html}</div>'
        f'<div style="font-size:11.5px;color:#8a94a7;margin-top:5px">{html.escape(meta)}</div>'
        f'{cta}</div></div>'
    )


def _section(title, items, social=False):
    if not items:
        body = '<div style="padding:22px 4px;color:#8a94a7;text-align:center">目前沒有符合條件的內容</div>'
    else:
        body = "".join(_card(item, social=social) for item in items)
    return (
        '<div style="background:#fff;border:1px solid #e5eaf1;border-radius:14px;padding:17px 18px;margin-top:16px">'
        '<div style="display:flex;justify-content:space-between;align-items:center;gap:10px;'
        'border-bottom:2px solid #0d2147;padding-bottom:10px">'
        f'<div style="font-size:19px;font-weight:800;color:#0d2147">{html.escape(title)}</div>'
        f'<div style="font-size:12px;color:#667085">{len(items)} 筆</div></div>'
        f'{body}</div>'
    )


def build_email(summary, suggestion, selected, slot):
    now = datetime.now(TAIPEI)
    # Include every item that passed the strict rolling-24h quality filters.
    ordered = sorted(
        selected,
        key=lambda item: legacy._parse_publish_time(item.get("publish_time")) or datetime.min.replace(tzinfo=TAIPEI),
        reverse=True,
    )
    news = [x for x in ordered if x.get("source") not in SOCIAL]
    social = [x for x in ordered if x.get("source") in SOCIAL]

    html_content = (
        '<div style="font-family:Arial,\'Noto Sans TC\',sans-serif;background:#f3f6fa;color:#14213d;padding:18px 8px;line-height:1.65">'
        '<div style="max-width:920px;margin:0 auto">'
        '<div style="background:#fff;border-top:5px solid #0d2147;border-radius:16px;padding:19px 22px">'
        '<div style="font-size:23px;font-weight:900;color:#102a56">國立臺北教育大學輿情快報</div>'
        f'<div style="font-size:12px;color:#6b7280;margin-top:5px">監測時間：{now.strftime("%Y/%m/%d %H:%M")}｜排程：{html.escape(slot)}｜過去 24 小時</div>'
        f'<div style="margin-top:15px;padding:14px 16px;background:#f5f8fc;border:1px solid #d9e4f0;border-radius:11px">'
        f'<div style="font-weight:800;color:#0d2147;margin-bottom:5px">本期摘要</div>'
        f'<div style="color:#2b3340">{html.escape(summary).replace(chr(10), "<br>")}</div></div>'
        f'<div style="margin-top:11px;padding:12px 16px;background:#fbfcfe;border:1px solid #e5eaf1;border-radius:11px">'
        f'<div style="font-weight:800;color:#0d2147;margin-bottom:4px">簡單建議</div>'
        f'<div style="color:#42526b">{html.escape(suggestion).replace(chr(10), "<br>")}</div></div>'
        f'<div style="margin-top:12px;font-size:12px;color:#667085">共 {len(ordered)} 則（新聞 {len(news)}｜社群 {len(social)}）</div>'
        '</div>'
        + _section("新聞報導", news, social=False)
        + _section("社群討論", social, social=True)
        + '<div style="font-size:11.5px;color:#7a8494;margin:14px 4px 0">本快報由公開新聞與社群資料自動蒐集與摘要；點選標題或來源按鈕即可前往來源。重要內容仍請以原始來源為準。</div>'
        '</div></div>'
    )

    lines = [
        "國立臺北教育大學輿情快報",
        f"監測時間：{now.strftime('%Y/%m/%d %H:%M')}｜排程：{slot}｜過去 24 小時",
        "",
        "本期摘要",
        summary,
        "",
        "簡單建議",
        suggestion,
        "",
        "新聞報導",
    ]
    for item in news:
        link, _ = best_link(item)
        lines.extend([f"• {item.get('title') or '（無標題）'}", f"  {item.get('source') or ''} · {_fmt_time(item)}", f"  {link}"])
    lines.extend(["", "社群討論"])
    for item in social:
        link, _ = best_link(item)
        lines.extend([f"• {item.get('title') or '（無標題）'}", f"  {item.get('source') or ''} · {_fmt_time(item)}", f"  {link}"])
    return html_content, "\n".join(lines)


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
        headers={"api-key": api_key, "accept": "application/json", "content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            status = resp.status
        data = json.loads(body) if body else {}
        message_id = data.get("messageId")
        ok = 200 <= status < 300 and bool(message_id)
        print(f"[digest] Brevo HTTP {status}; messageId={message_id or 'missing'}; html-cards=true recipient={recipient}")
        return ok
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        print(f"[digest] Brevo HTTP {exc.code}: {detail[:800]}")
        return False
    except Exception as exc:
        print(f"[digest] Brevo send failed: {exc}")
        return False


def build_and_send(settings, feed, slot):
    selected = legacy.select_items(feed, 24)
    summary, ai_generated = legacy.generate_ai_summary(selected)
    suggestion = legacy.safe_suggestion(selected)
    html_content, text_content = build_email(summary, suggestion, selected, slot)
    now = datetime.now(TAIPEI)
    prefix = str(settings.get("subject_prefix") or "【國北教大輿情快報】")
    subject = f"{prefix}{now.strftime('%Y/%m/%d')} {slot}"
    recipients = [str(x).strip() for x in settings.get("recipients", []) if str(x).strip()]
    if not recipients:
        print("[digest] no recipients configured")
        return False
    results = [submit_via_brevo(recipient, subject, html_content, text_content) for recipient in recipients]
    success_count = sum(1 for ok in results if ok)
    direct_count = sum(1 for item in selected if best_link(item)[1])
    fallback_count = sum(1 for item in selected if best_link(item)[0] and not best_link(item)[1])
    print(
        f"[digest] Brevo accepted {success_count}/{len(recipients)}; window=24h relevant={len(selected)} "
        f"direct_links={direct_count} index_fallback={fallback_count} ai_generated={ai_generated} attachment=none"
    )
    return success_count == len(recipients)
