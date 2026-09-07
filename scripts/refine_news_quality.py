#!/usr/bin/env python3
"""News quality gate for executive monitoring.

Goals:
1. Do not trust Google News RSS timestamps for publishers known to resurface old
   stories with fresh index timestamps. For those publishers, resolve an
   original article candidate and require a trustworthy publisher date.
2. Exclude items that refer only to NTUE's affiliated elementary school rather
   than the university itself.
"""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import collect_static as base

ROOT = Path(__file__).resolve().parents[1]
NEWS_FILE = ROOT / "frontend" / "public" / "data" / "news.json"
MAX_RECENT_DAYS = 35

AFFILIATE_SCHOOL_PHRASES = [
    "國立台北教育大學附設實驗國民小學",
    "國立台北教育大學附設實驗小學",
    "台北教育大學附設實驗國民小學",
    "台北教育大學附設實驗小學",
    "國北教大實小",
    "北教大實小",
    "國北實小",
]
UNIVERSITY_TERMS = [
    "國立台北教育大學",
    "台北教育大學",
    "國北教大",
    "國北教",
    "北教大",
    "ntue",
    "national taipei university of education",
]

# Publishers where the Google News RSS pubDate is not sufficient evidence of
# original publication time. Add more publishers here if repeated resurfacing
# problems are observed.
STRICT_PUBLISHERS = {
    "三立新聞": ("setn.com",),
    "三立新聞網": ("setn.com",),
    "setn": ("setn.com",),
}


def norm(value):
    return " ".join(str(value or "").replace("臺", "台").lower().split())


def school_only_mention(item):
    text = norm(" ".join([
        str(item.get("title") or ""),
        str(item.get("description") or ""),
        str(item.get("snippet") or ""),
    ]))
    matched_school = any(norm(p) in text for p in AFFILIATE_SCHOOL_PHRASES)
    if not matched_school:
        return False

    stripped = text
    for phrase in sorted(AFFILIATE_SCHOOL_PHRASES, key=len, reverse=True):
        stripped = stripped.replace(norm(phrase), " ")

    # If the university is independently mentioned outside the school name,
    # keep the item; otherwise it is about the elementary school only.
    return not any(norm(term) in stripped for term in UNIVERSITY_TERMS)


def publisher_domains(item):
    p = norm(item.get("publisher") or item.get("source") or "")
    for name, domains in STRICT_PUBLISHERS.items():
        if norm(name) in p:
            return domains
    return ()


def parse_iso_date(raw):
    raw = str(raw or "").strip()
    if not raw:
        return None
    raw = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=base.TAIPEI)
        return dt.astimezone(base.TAIPEI)
    except Exception:
        pass
    # Some publishers expose milliseconds or a space instead of T.
    m = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?", raw)
    if not m:
        return None
    try:
        return datetime(
            int(m.group(1)), int(m.group(2)), int(m.group(3)),
            int(m.group(4) or 12), int(m.group(5) or 0), int(m.group(6) or 0),
            tzinfo=base.TAIPEI,
        )
    except Exception:
        return None


def extract_publisher_date(page):
    patterns = [
        r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']article:published_time["\']',
        r'<meta[^>]+name=["\'](?:date|pubdate|publishdate|datePublished)["\'][^>]+content=["\']([^"\']+)',
        r'"datePublished"\s*:\s*"([^"]+)"',
        r'"dateCreated"\s*:\s*"([^"]+)"',
        r'"published_time"\s*:\s*"([^"]+)"',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, page, re.I | re.S):
            dt = parse_iso_date(match.group(1))
            if dt:
                return dt
    return None


def original_article_candidates(title, domains):
    candidates = []
    seen = set()
    clean_title = re.sub(r"\s+", " ", str(title or "")).strip()
    if not clean_title:
        return candidates
    for domain in domains:
        query = f'"{clean_title}" site:{domain}'
        try:
            rows = base.fetch_bing_web_rss(query, 12)
        except Exception as exc:
            print(f"[news_quality] bing lookup failed title={clean_title[:60]!r}: {exc}")
            continue
        for row in rows:
            url = str(row.get("url") or "")
            host = (urlparse(url).netloc or "").lower()
            if not any(host == d or host.endswith("." + d) for d in domains):
                continue
            key = url.split("#", 1)[0]
            if key in seen:
                continue
            seen.add(key)
            candidates.append(key)
    return candidates


def verify_original_date(item, domains):
    for url in original_article_candidates(item.get("title"), domains):
        try:
            page = base.request_text(url, timeout=14)
        except Exception:
            continue
        dt = extract_publisher_date(page)
        if not dt:
            continue
        return url, dt
    return None, None


def main():
    data = json.loads(NEWS_FILE.read_text(encoding="utf-8"))
    items = data.get("items", [])
    now = base.now_local()
    cutoff = now - timedelta(days=MAX_RECENT_DAYS)

    kept = []
    removed_school_only = 0
    removed_unverified_date = 0
    removed_stale_original = 0
    rewritten_dates = 0

    for item in items:
        if school_only_mention(item):
            removed_school_only += 1
            continue

        domains = publisher_domains(item)
        if domains and item.get("task") == "google_news":
            original_url, original_dt = verify_original_date(item, domains)
            if not original_dt:
                # Fail closed for known problematic publishers. A fresh Google
                # News index timestamp is not enough for an executive report.
                removed_unverified_date += 1
                continue
            if original_dt < cutoff or original_dt > now + timedelta(days=1):
                removed_stale_original += 1
                continue
            item = dict(item)
            item["publish_time"] = original_dt.isoformat()
            item["date_verified"] = True
            item["date_source"] = "publisher_original"
            if original_url:
                item["url"] = original_url
                item["original_url_verified"] = True
            rewritten_dates += 1

        kept.append(item)

    data["items"] = kept
    if isinstance(data.get("summary"), dict):
        data["summary"]["removed_school_only"] = removed_school_only
        data["summary"]["removed_unverified_news_date"] = removed_unverified_date
        data["summary"]["removed_stale_original_news"] = removed_stale_original
        data["summary"]["verified_original_news_dates"] = rewritten_dates

    NEWS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"[news_quality] kept={len(kept)} removed_school_only={removed_school_only} "
        f"removed_unverified_date={removed_unverified_date} "
        f"removed_stale_original={removed_stale_original} rewritten_dates={rewritten_dates}"
    )


if __name__ == "__main__":
    main()
