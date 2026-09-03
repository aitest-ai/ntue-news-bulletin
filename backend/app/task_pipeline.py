from datetime import datetime
from typing import Any, Callable, Dict, List

from . import parser


def _safe_task(name: str, fn: Callable[[str], List[Dict[str, Any]]], keyword: str) -> Dict[str, Any]:
    started = datetime.utcnow()
    try:
        items = fn(keyword) or []
        source_counts: Dict[str, int] = {}
        for item in items:
            source = str(item.get("source") or "Unknown")
            source_counts[source] = source_counts.get(source, 0) + 1
        return {
            "task": name,
            "status": "success",
            "items": items,
            "count": len(items),
            "source_counts": source_counts,
            "started_at": started.isoformat(),
            "finished_at": datetime.utcnow().isoformat(),
            "error": None,
        }
    except Exception as exc:
        return {
            "task": name,
            "status": "failed",
            "items": [],
            "count": 0,
            "source_counts": {},
            "started_at": started.isoformat(),
            "finished_at": datetime.utcnow().isoformat(),
            "error": str(exc)[:500],
        }


def _threads_direct(keyword: str) -> List[Dict[str, Any]]:
    """Use the dedicated Threads collector without letting its failure stop other sources."""
    _trace, posts = parser.collect_threads_posts(keyword)
    return posts or []


def _deduplicate(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    output: List[Dict[str, Any]] = []
    for item in items:
        url = str(item.get("url") or "").strip()
        fallback = f"{item.get('source')}::{item.get('title')}::{item.get('keyword')}"
        key = url if url else fallback
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def collect_keyword(keyword: str) -> Dict[str, Any]:
    """
    Run collection tasks independently.

    Google News, the broad social discovery path, and the dedicated Threads path
    are isolated so one broken source never aborts the entire keyword cycle.
    """
    tasks = [
        ("google_news", parser.fetch_google_news_rss),
        ("social_discovery", parser.fetch_social_posts),
        ("threads_direct", _threads_direct),
    ]
    results = [_safe_task(name, fn, keyword) for name, fn in tasks]

    combined: List[Dict[str, Any]] = []
    for result in results:
        combined.extend(result["items"])
    items = _deduplicate(combined)

    source_counts: Dict[str, int] = {}
    for item in items:
        source = str(item.get("source") or "Unknown")
        source_counts[source] = source_counts.get(source, 0) + 1

    return {
        "keyword": keyword,
        "status": "success" if any(r["status"] == "success" for r in results) else "failed",
        "tasks": [{k: v for k, v in r.items() if k != "items"} for r in results],
        "source_counts": source_counts,
        "items": items,
        "count": len(items),
    }
