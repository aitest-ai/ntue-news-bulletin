#!/usr/bin/env python3
import email.utils
import json
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

TAIPEI = timezone(timedelta(hours=8))
OUT_DIR = Path(__file__).resolve().parents[1] / "frontend" / "public" / "data"
OUT_FILE = OUT_DIR / "news.json"

KEYWORDS = [
    "國立臺北教育大學",
    "國北教大",
    "北教大",
    "NTUE",
    "National Taipei University of Education",
]

RELEVANCE_TERMS = [
    "國立臺北教育大學",
    "國立台北教育大學",
    "臺北教育大學",
    "台北教育大學",
    "國北教大",
    "國北教",
    "北教大",
    "國北",
    "NTUE",
    "National Taipei University of Education",
]

SOCIAL_TASKS = [
    {
        "task": "dcard",
        "source": "Dcard",
        "google_filter": "site:dcard.tw/f/ntue",
        "bing_filter": "site:dcard.tw/f/ntue",
        "domains": ("dcard.tw",),
        "days": 45,
    },
    {
        "task": "ptt",
        "source": "PTT",
        "google_filter": "site:ptt.cc",
        "bing_filter": "site:ptt.cc/bbs",
        "domains": ("ptt.cc",),
        "days": 60,
    },
    {
        "task": "threads",
        "source": "Threads",
        "google_filter": "site:threads.net OR site:threads.com",
        "bing_filter": "(site:threads.net OR site:threads.com)",
        "domains": ("threads.net", "threads.com"),
        "days": 60,
    },
    {
        "task": "instagram",
        "source": "Instagram",
        "google_filter": "site:instagram.com",
        "bing_filter": "site:instagram.com",
        "domains": ("instagram.com",),
        "days": 45,
    },
]


def now_local():
    return datetime.now(TAIPEI)


def normalize_text(value):
    return " ".join((value or "").replace("臺", "台").lower().split())


def relevance_keyword(text):
    norm = normalize_text(text)
    for term in RELEVANCE_TERMS:
        if normalize_text(term) in norm:
            for keyword in KEYWORDS:
                if normalize_text(keyword) in norm:
                    return keyword
            if "ntue" in norm:
                return "NTUE"
            if "北教" in norm or "國北" in norm:
                return "國北教大"
            return "國立臺北教育大學"
    return None


def parse_rfc822(value):
    if not value:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(TAIPEI)
        if local_dt.year <= 1971:
            return None
        return local_dt
    except Exception:
        return None


def fetch_google_news_rss(query, max_days, limit=100):
    encoded = urllib.parse.quote(query)
    rss_url = (
        "https://news.google.com/rss/search"
        f"?q={encoded}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    )
    request = urllib.request.Request(
        rss_url,
        headers={"User-Agent": "Mozilla/5.0 NTUE-Opinion-Monitor/4.0"},
    )
    cutoff = now_local() - timedelta(days=max_days)

    with urllib.request.urlopen(request, timeout=18) as response:
        root = ET.fromstring(response.read())

    rows = []
    for node in root.findall(".//item")[:limit]:
        raw_title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        pub_raw = (node.findtext("pubDate") or "").strip()
        source_node = node.find("source")
        if not raw_title or not link:
            continue

        local_dt = parse_rfc822(pub_raw)
        if not local_dt or local_dt < cutoff:
            continue

        publisher = (
            source_node.text.strip()
            if source_node is not None and source_node.text
            else "Google News"
        )
        title = raw_title.rsplit(" - ", 1)[0].strip() if " - " in raw_title else raw_title
        rows.append({
            "title": title,
            "url": link,
            "publisher": publisher,
            "publish_time": local_dt.isoformat(),
            "description": "",
            "discovery": "google_news",
        })
    return rows


def fetch_bing_web_rss(query, limit=50):
    encoded = urllib.parse.quote(query)
    rss_url = f"https://www.bing.com/search?q={encoded}&format=rss&setlang=zh-Hant&mkt=zh-TW"
    request = urllib.request.Request(
        rss_url,
        headers={"User-Agent": "Mozilla/5.0 NTUE-Opinion-Monitor/4.0"},
    )
    with urllib.request.urlopen(request, timeout=18) as response:
        root = ET.fromstring(response.read())

    rows = []
    for node in root.findall(".//item")[:limit]:
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        description = (node.findtext("description") or "").strip()
        pub_raw = (node.findtext("pubDate") or "").strip()
        if not title or not link:
            continue
        dt = parse_rfc822(pub_raw)
        rows.append({
            "title": title,
            "url": link,
            "publisher": urlparse(link).netloc or "Bing Web",
            "publish_time": dt.isoformat() if dt else None,
            "description": description,
            "discovery": "bing_web",
        })
    return rows


def fetch_news_task():
    items = []
    seen = set()
    keyword_counts = {}

    # Search every alias separately and keep up to 100 results per alias.
    for keyword in KEYWORDS:
        query = f'"{keyword}" when:30d'
        rows = fetch_google_news_rss(query, 30, limit=100)
        keyword_counts[keyword] = len(rows)
        for row in rows:
            key = row["url"]
            if key in seen:
                continue
            seen.add(key)
            items.append({
                "title": row["title"],
                "url": row["url"],
                "source": row["publisher"],
                "publisher": row["publisher"],
                "publish_time": row["publish_time"],
                "discovered_at": now_local().isoformat(),
                "keyword": keyword,
                "task": "google_news",
                "discovery": "google_news",
            })
    return items, keyword_counts


def domain_allowed(url, domains):
    host = (urlparse(url).netloc or "").lower()
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def fetch_social_task(spec):
    items = []
    seen_urls = set()
    seen_titles = set()
    engine_counts = {"google_news": 0, "bing_web": 0}

    # Per-keyword queries are intentionally used instead of one large OR query.
    for keyword in KEYWORDS:
        queries = [
            ("google_news", f'"{keyword}" {spec["google_filter"]} when:{spec["days"]}d'),
            ("bing_web", f'"{keyword}" {spec["bing_filter"]}'),
        ]
        for engine, query in queries:
            try:
                rows = (
                    fetch_google_news_rss(query, spec["days"], limit=100)
                    if engine == "google_news"
                    else fetch_bing_web_rss(query, limit=50)
                )
            except Exception as exc:
                print(f'[{spec["task"]}:{engine}:{keyword}] fallback failed: {exc}', file=sys.stderr)
                continue

            for row in rows:
                # Bing is a normal web search, so enforce the expected source domain.
                if engine == "bing_web" and not domain_allowed(row["url"], spec["domains"]):
                    continue

                searchable = f'{row["title"]} {row.get("description", "")}'
                matched = relevance_keyword(searchable)
                if not matched:
                    continue

                url_key = row["url"].split("#", 1)[0]
                title_key = (normalize_text(row["title"]), spec["source"])
                if url_key in seen_urls or title_key in seen_titles:
                    continue
                seen_urls.add(url_key)
                seen_titles.add(title_key)
                engine_counts[engine] += 1

                items.append({
                    "title": row["title"],
                    "url": row["url"],
                    "source": spec["source"],
                    "publisher": row["publisher"],
                    "publish_time": row["publish_time"],
                    "discovered_at": now_local().isoformat(),
                    "keyword": matched,
                    "task": spec["task"],
                    "discovery": engine,
                })

    return items, engine_counts


def load_previous():
    if not OUT_FILE.exists():
        return []
    try:
        data = json.loads(OUT_FILE.read_text(encoding="utf-8"))
        return data.get("items", []) if isinstance(data, dict) else []
    except Exception:
        return []


def deduplicate(items):
    seen_urls = set()
    seen_titles = set()
    result = []
    for item in items:
        url_key = (item.get("url") or "").split("#", 1)[0]
        title_key = (normalize_text(item.get("title")), normalize_text(item.get("source")))
        if (url_key and url_key in seen_urls) or title_key in seen_titles:
            continue
        if url_key:
            seen_urls.add(url_key)
        seen_titles.add(title_key)
        result.append(item)
    return result


def previous_item_is_valid(item):
    if item.get("task") == "google_news":
        return True
    searchable = f'{item.get("title", "")} {item.get("description", "")}'
    return bool(relevance_keyword(searchable))


def retention_datetime(item):
    # Published date is preferred. Discovery time is only a retention fallback,
    # never displayed as if it were the publication date.
    for key in ("publish_time", "discovered_at"):
        value = item.get(key)
        if not value:
            continue
        try:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TAIPEI)
            if dt.year > 1971:
                return dt
        except Exception:
            pass
    return None


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    health = []
    fresh = []

    try:
        news_items, keyword_counts = fetch_news_task()
        fresh.extend(news_items)
        health.append({
            "task": "google_news",
            "source": "新聞媒體",
            "status": "healthy",
            "count": len(news_items),
            "error": None,
            "keyword_counts": keyword_counts,
        })
        print(f"[google_news] {len(news_items)} unique items from {len(KEYWORDS)} keyword searches")
    except Exception as exc:
        health.append({
            "task": "google_news",
            "source": "新聞媒體",
            "status": "failed",
            "count": 0,
            "error": str(exc)[:240],
        })
        print(f"[google_news] FAILED: {exc}", file=sys.stderr)

    for spec in SOCIAL_TASKS:
        try:
            task_items, engine_counts = fetch_social_task(spec)
            fresh.extend(task_items)
            health.append({
                "task": spec["task"],
                "source": spec["source"],
                "status": "healthy",
                "count": len(task_items),
                "error": None,
                "engine_counts": engine_counts,
            })
            print(
                f'[{spec["task"]}] {len(task_items)} relevant items '
                f'(Google News {engine_counts["google_news"]}, Bing Web {engine_counts["bing_web"]})'
            )
        except Exception as exc:
            health.append({
                "task": spec["task"],
                "source": spec["source"],
                "status": "failed",
                "count": 0,
                "error": str(exc)[:240],
            })
            print(f'[{spec["task"]}] FAILED: {exc}', file=sys.stderr)

    previous = [item for item in load_previous() if previous_item_is_valid(item)]
    combined = deduplicate(fresh + previous)
    cutoff = now_local() - timedelta(days=90)
    kept = []
    for item in combined:
        dt = retention_datetime(item)
        if dt and dt >= cutoff:
            kept.append(item)

    kept.sort(
        key=lambda x: x.get("publish_time") or x.get("discovered_at") or "",
        reverse=True,
    )
    kept = kept[:1000]

    news_publishers = sorted({
        item.get("publisher") or item.get("source")
        for item in kept
        if item.get("task") == "google_news"
    })

    payload = {
        "schema_version": 5,
        "updated_at": now_local().isoformat(),
        "keywords": KEYWORDS,
        "items": kept,
        "source_health": health,
        "summary": {
            "total": len(kept),
            "fresh_this_run": len(fresh),
            "healthy_tasks": sum(1 for h in health if h["status"] == "healthy"),
            "failed_tasks": sum(1 for h in health if h["status"] == "failed"),
            "news_publishers": len(news_publishers),
        },
    }
    OUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(kept)} items, {len(news_publishers)} news publishers -> {OUT_FILE}")


if __name__ == "__main__":
    main()
