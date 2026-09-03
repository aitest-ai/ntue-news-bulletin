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

# Used only for relevance validation. These aliases are deliberately specific enough
# to keep NTUE-related student/community posts while rejecting unrelated search noise.
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

TASKS = [
    ("google_news", "新聞媒體", None, 14),
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
            # Prefer a canonical monitoring keyword when possible.
            for keyword in KEYWORDS:
                if normalize_text(keyword) in norm:
                    return keyword
            if "ntue" in norm:
                return "NTUE"
            if "北教" in norm or "國北" in norm:
                return "國北教大"
            return "國立臺北教育大學"
    return None


def fetch_task(task_name, display_source, site_filter, max_days):
    base = keyword_query()
    query = f"{base} {site_filter or ''} when:{max_days}d".strip()
    encoded = urllib.parse.quote(query)
    rss_url = (
        "https://news.google.com/rss/search"
        f"?q={encoded}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    )
    request = urllib.request.Request(
        rss_url,
        headers={"User-Agent": "Mozilla/5.0 NTUE-Opinion-Monitor/3.1"},
    )
    cutoff = now_local() - timedelta(days=max_days)

    with urllib.request.urlopen(request, timeout=15) as response:
        root = ET.fromstring(response.read())

    items = []
    for node in root.findall(".//item")[:40]:
        raw_title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        pub_raw = (node.findtext("pubDate") or "").strip()
        source_node = node.find("source")

        if not raw_title or not link or not pub_raw:
            continue

        title = raw_title.rsplit(" - ", 1)[0].strip() if " - " in raw_title else raw_title
        matched = relevance_keyword(title)
        if not matched:
            continue

        try:
            dt = email.utils.parsedate_to_datetime(pub_raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            local_dt = dt.astimezone(TAIPEI)
        except Exception:
            continue

        # Unknown, malformed, or 1970-like dates are discarded instead of relabeled as new.
        if local_dt.year <= 1971 or local_dt < cutoff:
            continue

        publisher = (
            source_node.text.strip()
            if source_node is not None and source_node.text
            else "Google News"
        )
        source = display_source if display_source != "新聞媒體" else publisher
        items.append(
            {
                "title": title,
                "url": link,
                "source": source,
                "publisher": publisher,
                "publish_time": local_dt.isoformat(),
                "keyword": matched,
                "task": task_name,
            }
        )

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


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    health = []
    fresh = []

    for task_name, source, site_filter, max_days in TASKS:
        try:
            task_items = fetch_task(task_name, source, site_filter, max_days)
            fresh.extend(task_items)
            health.append(
                {
                    "task": task_name,
                    "source": source,
                    "status": "healthy",
                    "count": len(task_items),
                    "error": None,
                }
            )
            print(f"[{task_name}] {len(task_items)} relevant items")
        except Exception as exc:
            health.append(
                {
                    "task": task_name,
                    "source": source,
                    "status": "failed",
                    "count": 0,
                    "error": str(exc)[:240],
                }
            )
            print(f"[{task_name}] FAILED: {exc}", file=sys.stderr)

    # Keep recent previous items through temporary source outages, but re-validate
    # them with the current relevance rules so historical false positives disappear.
    previous = [item for item in load_previous() if relevance_keyword(item.get("title", ""))]
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
    kept = kept[:300]

    payload = {
        "schema_version": 3,
        "updated_at": now_local().isoformat(),
        "keywords": KEYWORDS,
        "items": kept,
        "source_health": health,
        "summary": {
            "total": len(kept),
            "fresh_this_run": len(fresh),
            "healthy_tasks": sum(1 for h in health if h["status"] == "healthy"),
            "failed_tasks": sum(1 for h in health if h["status"] == "failed"),
        },
    }
    OUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(kept)} items -> {OUT_FILE}")


if __name__ == "__main__":
    main()
