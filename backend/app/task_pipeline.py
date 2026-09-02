from datetime import datetime
from typing import Callable, Dict, List, Any

from . import parser


def _safe_task(name: str, fn: Callable[[str], List[Dict[str, Any]]], keyword: str) -> Dict[str, Any]:
    started = datetime.utcnow()
    try:
        items = fn(keyword) or []
        return {
            "task": name,
            "status": "success",
            "items": items,
            "count": len(items),
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
            "started_at": started.isoformat(),
            "finished_at": datetime.utcnow().isoformat(),
            "error": str(exc)[:500],
        }


def collect_keyword(keyword: str) -> Dict[str, Any]:
    """Run each source independently so one broken scraper never stops the cycle."""
    tasks = [
        ("google_news", parser.fetch_google_news_rss),
        ("social_search", parser.fetch_social_posts),
    ]
    results = [_safe_task(name, fn, keyword) for name, fn in tasks]
    items: List[Dict[str, Any]] = []
    for result in results:
        items.extend(result["items"])

    return {
        "keyword": keyword,
        "status": "success" if any(r["status"] == "success" for r in results) else "failed",
        "tasks": [{k: v for k, v in r.items() if k != "items"} for r in results],
        "items": items,
        "count": len(items),
    }
