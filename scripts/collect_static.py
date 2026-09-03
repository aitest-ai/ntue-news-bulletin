#!/usr/bin/env python3
import email.utils
import json
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
    ("dcard", "Dcard", "site:dcard.tw/f/ntue", 30),
    ("ptt", "PTT", "site:ptt.cc", 30),
    ("threads", "Threads", "site:threads.net OR site:threads.com", 30),
    ("instagram", "Instagram", "site:instagram.com", 30),
]


def now_local():
    return datetime.now(TAIPEI)


def normalize_text(value):
    return (value or "").replace("臺", "台").lower().strip()


def keyword_query():
    return "(" + " OR ".join(f'\"{word}\"' for word in KEYWORDS) + ")"


def relevance_keyword(title):
    norm = normalize_text(title)
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


def fetch_rss(query, max_days, user_agent="Mozilla/5.0 NTUE-Opinion-Monitor/3.2"):
    encoded = urllib.parse.quote(query)
    rss_url = (
        "https://news.google.com/rss/search"
        f"?q={encoded}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    )
    request = urllib.request.Request(rss_url, headers={"User-Agent": user_agent})
    cutoff = now_local() - timedelta(days=max_days)

    with urllib.request.urlopen(request, timeout=15) as response:
        root = ET.fromstring(response.read())

    rows = []
    for node in root.findall(".//item")[:40]:
        raw_title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        pub_raw = (node.findtext("pubDate") or "").strip()
        source_node = node.find("source")
        if not raw_title or not link or not pub_raw:
            continue

        try:
            dt = email.utils.parsedate_to_datetime(pub_raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            local_dt = dt.astimezone(TAIPEI)
        except Exception:
            continue

        if local_dt.year <= 1971 or local_dt < cutoff:
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
        })
    return rows


def fetch_news_task():
    """Search each monitoring keyword separately to preserve publisher diversity.

    News results are trusted based on the Google News keyword query itself; unlike
    social posts, the headline is not required to repeat the school name because
    many legitimate news headlines mention a person/event while the article body
    carries the NTUE connection.
    """
    items = []
    seen = set()
    keyword_counts = {}

    for keyword in KEYWORDS:
        query = f'"{keyword}" when:14d'
        rows = fetch_rss(query, 14)
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
                "keyword": keyword,
                "task": "google_news",
            })

    return items, keyword_counts


def fetch_social_task(task_name, display_source, site_filter, max_days):
    query = f"{keyword_query()} {site_filter} when:{max_days}d".strip()
    rows = fetch_rss(query, max_days)
    items = []
    for row in rows:
        matched = relevance_keyword(row["title"])
        if not matched:
            continue
        items.append({
            "title": row["title"],
            "url": row["url"],
            "source": display_source,
            "publisher": row["publisher"],
            "publish_time": row["publish_time"],
            "keyword": matched,
            "task": task_name,
        })
    return items


def load_previous():
    if not OUT_FILE.exists():
        return []
    try:
        data = json.loads(OUT_FILE.read_text(encoding="utf-8"))
        return data.get("items", []) if isinstance(data, dict) else []
    except Exception:
        return []


def deduplicate(items):
    seen = set()
    result = []
    for item in items:
        key = item.get("url") or (
            normalize_text(item.get("title")),
            normalize_text(item.get("source")),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def previous_item_is_valid(item):
    if item.get("task") == "google_news":
        return True
    return bool(relevance_keyword(item.get("title", "")))


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

    for task_name, source, site_filter, max_days in SOCIAL_TASKS:
        try:
            task_items = fetch_social_task(task_name, source, site_filter, max_days)
            fresh.extend(task_items)
            health.append({
                "task": task_name,
                "source": source,
                "status": "healthy",
                "count": len(task_items),
                "error": None,
            })
            print(f"[{task_name}] {len(task_items)} relevant items")
        except Exception as exc:
            health.append({
                "task": task_name,
                "source": source,
                "status": "failed",
                "count": 0,
                "error": str(exc)[:240],
            })
            print(f"[{task_name}] FAILED: {exc}", file=sys.stderr)

    previous = [item for item in load_previous() if previous_item_is_valid(item)]
    combined = deduplicate(fresh + previous)
    cutoff = now_local() - timedelta(days=30)
    kept = []
    for item in combined:
        try:
            dt = datetime.fromisoformat(item.get("publish_time", ""))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TAIPEI)
            if dt >= cutoff:
                kept.append(item)
        except Exception:
            continue

    kept.sort(key=lambda x: x.get("publish_time", ""), reverse=True)
    kept = kept[:500]

    news_publishers = sorted({
        item.get("publisher") or item.get("source")
        for item in kept
        if item.get("task") == "google_news"
    })

    payload = {
        "schema_version": 4,
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
