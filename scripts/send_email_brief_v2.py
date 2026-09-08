#!/usr/bin/env python3
"""HTML-only NTUE bulletin with mobile-friendly dashboard-style source cards."""
from __future__ import annotations

import html
import json
import os
import re
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


def _clean_summary(text):
    """Remove letter-like greetings so the bulletin starts directly with content."""
    value = str(text or "").strip()
    value = re.sub(
        r"^(?:各位)?(?:主管|長官|同仁)?(?:您好|好)[！!，,。：:\s]*",
        "",
        value,
        flags=re.I,
    ).strip()
    value = re.sub(r"^(?:您好|大家好)[！!，,。：:\s]*", "", value, flags=re.I).strip()
    return value or "過去 24 小時內未產生可用摘要，請直接參閱下方來源。"


def _platform_visual(item):
    """Small image-free avatar that survives clients blocking remote images."""
    source = str(item.get("source") or "").strip()
    s = source.lower()
    if "yahoo" in s:
        return "Y!", "#6f2dbd", "#ffffff"
    if source == "Dcard" or "dcard" in s:
        return "D", "#006aa6", "#ffffff"
    if source == "Threads" or "threads" in s:
        return "@", "#111111", "#ffffff"
    if source == "Instagram" or "instagram" in s:
        return "IG", "#b13b78", "#ffffff"
    if source == "PTT" or "ptt" in s:
        return "PTT", "#263238", "#ffffff"
    if "facebook" in s or source == "Facebook":
        return "f", "#1877f2", "#ffffff"
    if source in SOCIAL:
        return "社", "#a65a16", "#ffffff"
    return "新", "#315caa", "#ffffff"


def _compact_snippet(item, title):
    snippet = " ".join(str(item.get("snippet") or "").split())
    if not snippet or snippet == title or snippet.startswith(title):
        return ""
    if len(snippet) > 105:
        snippet = snippet[:102].rstrip() + "…"
    return snippet


def _card(item, social=False):
    title = " ".join(str(item.get("title") or "（無標題）").split())
    source = str(item.get("source") or "公開來源").strip()
    publisher = str(item.get("publisher") or "").strip()
    link, direct = best_link(item)
    avatar, avatar_bg, avatar_fg = _platform_visual(item)
    snippet = _compact_snippet(item, title)

    meta_parts = [source]
    if publisher and publisher.lower() != source.lower():
        meta_parts.append(publisher)
    meta_parts.append(_fmt_time(item))
    meta = " · ".join(meta_parts)

    if link:
        title_html = (
            f'<a href="{html.escape(link, quote=True)}" '
            'style="color:#17233b;text-decoration:none;font-size:16px;font-weight:800;line-height:1.48">'
            f'{html.escape(title)}</a>'
        )
        cta = (
            f'<a href="{html.escape(link, quote=True)}" '
            'style="display:inline-block;margin-top:8px;color:#1769aa;text-decoration:none;font-size:13px;font-weight:800">'
            + ("查看原文&nbsp;→" if direct else "開啟來源&nbsp;→") + "</a>"
        )
    else:
        title_html = f'<span style="color:#17233b;font-size:16px;font-weight:800;line-height:1.48">{html.escape(title)}</span>'
        cta = ""

    snippet_html = (
        f'<div style="font-size:13px;line-height:1.55;color:#5f6b7a;margin-top:6px">{html.escape(snippet)}</div>'
        if snippet else ""
    )

    # Table layout is much more reliable than flexbox in Gmail/Outlook mobile clients.
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="width:100%;border-collapse:collapse;border-bottom:1px solid #e8edf3">'
        '<tr>'
        '<td width="56" valign="top" style="width:56px;padding:15px 12px 15px 0">'
        f'<div style="width:44px;height:44px;line-height:44px;border-radius:50%;text-align:center;'
        f'font-family:Arial,sans-serif;font-size:{"12" if len(avatar)>2 else "16"}px;font-weight:900;'
        f'background:{avatar_bg};color:{avatar_fg};">{html.escape(avatar)}</div>'
        '</td>'
        '<td valign="top" style="padding:14px 0 15px 0">'
        f'<div>{title_html}</div>'
        f'<div style="font-size:12px;color:#7b8798;margin-top:5px;line-height:1.45">{html.escape(meta)}</div>'
        f'{snippet_html}{cta}'
        '</td>'
        '</tr></table>'
    )


def _section(title, items, social=False):
    if not items:
        body = '<div style="padding:22px 2px;color:#8a94a7;text-align:center;font-size:13px">目前沒有符合條件的內容</div>'
    else:
        body = "".join(_card(item, social=social) for item in items)
    return (
        '<div style="background:#ffffff;border:1px solid #dfe6ee;border-radius:14px;padding:16px 18px;margin-top:14px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;border-collapse:collapse">'
        '<tr><td style="padding-bottom:9px;border-bottom:2px solid #17345e">'
        f'<span style="font-size:19px;font-weight:900;color:#17345e">{html.escape(title)}</span>'
        f'<span style="font-size:12px;color:#7a8494;margin-left:7px">{len(items)} 筆</span>'
        '</td></tr></table>'
        f'{body}</div>'
    )


def build_email(summary, suggestion, selected, slot):
    now = datetime.now(TAIPEI)
    ordered = sorted(
        selected,
        key=lambda item: legacy._parse_publish_time(item.get("publish_time")) or datetime.min.replace(tzinfo=TAIPEI),
        reverse=True,
    )
    news = [x for x in ordered if x.get("source") not in SOCIAL]
    social = [x for x in ordered if x.get("source") in SOCIAL]
    summary = _clean_summary(summary)

    html_content = (
        '<div style="margin:0;padding:0;background:#f2f5f9;font-family:Arial,\'Noto Sans TC\',sans-serif;color:#17233b;line-height:1.65">'
        '<div style="max-width:760px;margin:0 auto;padding:14px 8px 24px">'
        '<div style="background:#ffffff;border-top:5px solid #17345e;border-radius:14px;padding:20px 20px 18px">'
        '<div style="font-size:24px;font-weight:900;color:#17345e;line-height:1.25">國立臺北教育大學輿情快報</div>'
        f'<div style="font-size:12px;color:#7b8798;margin-top:6px">{now.strftime("%Y/%m/%d %H:%M")}　｜　過去 24 小時　｜　排程 {html.escape(slot)}</div>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:15px;width:100%;border-collapse:collapse">'
        '<tr>'
        f'<td style="width:33%;padding:10px 6px;text-align:center;background:#f5f8fc;border-radius:9px 0 0 9px"><div style="font-size:20px;font-weight:900;color:#17345e">{len(ordered)}</div><div style="font-size:11px;color:#7b8798">全部</div></td>'
        f'<td style="width:33%;padding:10px 6px;text-align:center;background:#f5f8fc;border-left:1px solid #dfe6ee"><div style="font-size:20px;font-weight:900;color:#315caa">{len(news)}</div><div style="font-size:11px;color:#7b8798">新聞</div></td>'
        f'<td style="width:34%;padding:10px 6px;text-align:center;background:#f5f8fc;border-left:1px solid #dfe6ee;border-radius:0 9px 9px 0"><div style="font-size:20px;font-weight:900;color:#a65a16">{len(social)}</div><div style="font-size:11px;color:#7b8798">社群</div></td>'
        '</tr></table>'
        '<div style="margin-top:15px;padding:14px 15px;background:#f5f8fc;border:1px solid #d9e4f0;border-radius:10px">'
        '<div style="font-size:14px;font-weight:900;color:#17345e;margin-bottom:5px">本期摘要</div>'
        f'<div style="font-size:14px;color:#293548;line-height:1.7">{html.escape(summary).replace(chr(10), "<br>")}</div></div>'
        '<div style="margin-top:10px;padding:12px 15px;background:#fbfcfe;border:1px solid #e4e9f0;border-radius:10px">'
        '<div style="font-size:13px;font-weight:900;color:#17345e;margin-bottom:4px">簡單建議</div>'
        f'<div style="font-size:13px;color:#536176;line-height:1.65">{html.escape(suggestion).replace(chr(10), "<br>")}</div></div>'
        '</div>'
        + _section("新聞報導", news, social=False)
        + _section("社群討論", social, social=True)
        + '<div style="font-size:11px;color:#8590a0;line-height:1.6;margin:13px 5px 0">本快報自動蒐集公開新聞與社群內容並進行摘要。點選標題或「查看原文」可直接前往來源；重要資訊仍以原始來源為準。</div>'
        '</div></div>'
    )

    lines = [
        "國立臺北教育大學輿情快報",
        f"{now.strftime('%Y/%m/%d %H:%M')}｜過去 24 小時｜排程 {slot}",
        f"共 {len(ordered)} 則（新聞 {len(news)}｜社群 {len(social)}）",
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
        print(f"[digest] Brevo HTTP {status}; messageId={message_id or 'missing'}; html-cards=v3 recipient={recipient}")
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
        f"direct_links={direct_count} index_fallback={fallback_count} ai_generated={ai_generated} attachment=none ui=v3"
    )
    return success_count == len(recipients)
