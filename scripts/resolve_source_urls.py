#!/usr/bin/env python3
"""Resolve recent Google News discovery URLs to original sources.

Resolution order:
1. Decode Google News' article wrapper with googlenewsdecoder.
2. Validate the decoded host against the expected source when one is known.
3. Fall back to exact-title source-site search.
4. If neither works, preserve the Google News URL as a clickable fallback.

The email and dashboard therefore never lose a source link, while verified direct
links are preferred whenever they can be obtained confidently.
"""
from __future__ import annotations

import json
from datetime import timedelta
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

import collect_static as base

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:
    gnewsdecoder = None

ROOT = Path(__file__).resolve().parents[1]
NEWS_FILE = ROOT / "frontend" / "public" / "data" / "news.json"
LOOKUP_HOURS = 72

DOMAIN_HINTS = {
    "dcard": ("dcard.tw",),
    "instagram": ("instagram.com",),
    "ptt": ("ptt.cc",),
    "三立": ("setn.com",),
    "聯合": ("udn.com",),
    "自由時報": ("ltn.com.tw",),
    "中央社": ("cna.com.tw",),
    "ettoday": ("ettoday.net",),
    "中時": ("chinatimes.com",),
    "tvbs": ("tvbs.com.tw",),
    "公視": ("pts.org.tw",),
    "nownews": ("nownews.com",),
}


def norm(value):
    return " ".join(str(value or "").replace("臺", "台").lower().split())


def is_google_news(url):
    host = (urlparse(str(url or "")).netloc or "").lower()
    return host in {"news.google.com", "www.news.google.com"}


def parse_dt(raw):
    if not raw:
        return None
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=base.TAIPEI)
        return dt.astimezone(base.TAIPEI)
    except Exception:
        return None


def expected_domains(item):
    label = norm(f"{item.get('source', '')} {item.get('publisher', '')}")
    for key, domains in DOMAIN_HINTS.items():
        if key in label:
            return domains
    return ()


def domain_ok(url, domains):
    if not domains:
        return True
    host = (urlparse(url).netloc or "").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def similarity(a, b):
    a = norm(a)
    b = norm(b)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def decode_google_news(url, domains):
    if gnewsdecoder is None:
        return ""
    try:
        result = gnewsdecoder(url, interval=None)
        if not isinstance(result, dict) or not result.get("status"):
            return ""
        decoded = str(result.get("decoded_url") or "").strip()
        if not decoded.startswith(("http://", "https://")) or is_google_news(decoded):
            return ""
        if not domain_ok(decoded, domains):
            return ""
        return decoded.split("#", 1)[0]
    except Exception as exc:
        print(f"[source_urls] Google decode failed: {exc}")
        return ""


def candidate_rows(title, domains):
    rows = []
    queries = []
    if domains:
        for domain in domains:
            queries.append(f'"{title}" site:{domain}')
    else:
        queries.append(f'"{title}"')
    for query in queries:
        try:
            rows.extend(base.fetch_bing_web_rss(query, 12))
        except Exception as exc:
            print(f"[source_urls] Bing lookup failed query={query[:100]!r}: {exc}")
        if rows:
            break
    if not rows:
        for query in queries:
            try:
                rows.extend(base.fetch_duckduckgo_html(query, 12))
            except Exception as exc:
                print(f"[source_urls] DDG lookup failed query={query[:100]!r}: {exc}")
            if rows:
                break
    return rows


def title_search_url(title, domains):
    best = ""
    best_score = 0.0
    for row in candidate_rows(title, domains):
        candidate = str(row.get("url") or "").strip()
        if not candidate.startswith(("http://", "https://")) or is_google_news(candidate):
            continue
        if not domain_ok(candidate, domains):
            continue
        score = similarity(title, row.get("title"))
        required = 0.56 if domains else 0.78
        if score >= required and score > best_score:
            best = candidate.split("#", 1)[0]
            best_score = score
    return best, best_score


def resolve_item(item):
    url = str(item.get("url") or "").strip()
    if not is_google_news(url):
        return item, False

    title = str(item.get("title") or "").strip()
    domains = expected_domains(item)
    out = dict(item)
    out["google_news_url"] = url

    decoded = decode_google_news(url, domains)
    if decoded:
        out["url"] = decoded
        out["original_url"] = decoded
        out["original_url_verified"] = True
        out["url_source"] = "google_news_decoded"
        return out, True

    if title:
        searched, score = title_search_url(title, domains)
        if searched:
            out["url"] = searched
            out["original_url"] = searched
            out["original_url_verified"] = True
            out["url_source"] = "exact_title_source_lookup"
            out["url_match_score"] = round(score, 3)
            return out, True

    out["url_source"] = "google_news_index"
    return out, False


def main():
    data = json.loads(NEWS_FILE.read_text(encoding="utf-8"))
    items = data.get("items", [])
    now = base.now_local()
    cutoff = now - timedelta(hours=LOOKUP_HOURS)
    resolved = 0
    unresolved = 0
    untouched = 0
    cache = {}
    new_items = []

    for item in items:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        dt = parse_dt(item.get("publish_time"))
        if not is_google_news(url) or dt is None or dt < cutoff:
            new_items.append(item)
            untouched += 1
            continue

        cache_key = url
        if cache_key in cache:
            cached_url = cache[cache_key]
            out = dict(item)
            out["google_news_url"] = url
            if cached_url:
                out["url"] = cached_url
                out["original_url"] = cached_url
                out["original_url_verified"] = True
                out["url_source"] = "google_news_decoded_cached"
                resolved += 1
            else:
                out["url_source"] = "google_news_index"
                unresolved += 1
            new_items.append(out)
            continue

        out, ok = resolve_item(item)
        cache[cache_key] = out.get("original_url") if ok else ""
        new_items.append(out)
        if ok:
            resolved += 1
        else:
            unresolved += 1

    data["items"] = new_items
    if isinstance(data.get("summary"), dict):
        data["summary"]["resolved_recent_source_urls"] = resolved
        data["summary"]["google_news_fallback_urls"] = unresolved
    NEWS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[source_urls] resolved={resolved} google_fallback={unresolved} untouched={untouched}")


if __name__ == "__main__":
    main()
