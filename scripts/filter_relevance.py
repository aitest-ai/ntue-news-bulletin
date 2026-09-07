#!/usr/bin/env python3
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
NEWS_FILE = ROOT / "frontend" / "public" / "data" / "news.json"
SOCIAL = {"Dcard", "PTT", "Threads", "Instagram"}
TERMS = [
    "國立臺北教育大學", "國立台北教育大學", "臺北教育大學", "台北教育大學",
    "國北教大", "國北教", "北教大", "ntue", "national taipei university of education",
]
TAIPEI = timezone(timedelta(hours=8))
MAX_THREADS_AGE_DAYS = 45


def norm(value):
    return " ".join(str(value or "").replace("臺", "台").lower().split())


def _valid_threads_date(item):
    raw = str(item.get("publish_time") or "").strip()
    if not raw:
        return False
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TAIPEI)
        dt = dt.astimezone(TAIPEI)
    except Exception:
        return False
    now = datetime.now(TAIPEI)
    return now - timedelta(days=MAX_THREADS_AGE_DAYS) <= dt <= now + timedelta(days=1)


def _meaningful_threads_title(item):
    title = str(item.get("title") or "").strip()
    if not title:
        return False

    publisher = str(item.get("publisher") or "").strip()
    probe = norm(title)
    if publisher:
        probe = re.sub(rf"^@?{re.escape(norm(publisher))}\b", "", probe).strip()

    probe = re.sub(r"(?<!\d)\d{1,3}\s*(?:週|天|小時|分鐘)(?:前)?", " ", probe)
    probe = re.sub(r"\b20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}\b", " ", probe)

    for token in [
        "國立臺北教育大學", "國立台北教育大學", "臺北教育大學", "台北教育大學",
        "國北教大", "國北教", "北教大", "國北", "ntue",
    ]:
        probe = probe.replace(norm(token), " ")

    probe = re.sub(r"[\W_]+", "", probe)
    return len(probe) >= 6


def keep(item):
    source = str(item.get("source") or "")
    task = str(item.get("task") or "")
    url = str(item.get("url") or "")
    host = (urlparse(url).netloc or "").lower()

    # Threads gets a stricter evidence-quality gate. Search engines can surface
    # months-old posts with no date and Threads cards can expose only the account
    # header; neither is useful in a current executive report.
    if source == "Threads" or task == "threads":
        if not _valid_threads_date(item):
            return False
        if not _meaningful_threads_title(item):
            return False
        return True

    # Other social collectors already perform relevance checks using search text/snippets.
    if source in SOCIAL or task in {"dcard", "ptt", "instagram"}:
        return True

    haystack = norm(" ".join([
        str(item.get("title") or ""),
        str(item.get("source") or ""),
        str(item.get("publisher") or ""),
    ]))
    if any(norm(term) in haystack for term in TERMS):
        return True
    if host.endswith("ntue.edu.tw"):
        return True
    return False


def main():
    data = json.loads(NEWS_FILE.read_text(encoding="utf-8"))
    items = data.get("items", [])
    kept = []
    removed_unrelated = 0
    removed_threads_quality = 0

    for item in items:
        is_thread = item.get("source") == "Threads" or item.get("task") == "threads"
        if keep(item):
            kept.append(item)
        elif is_thread:
            removed_threads_quality += 1
        else:
            removed_unrelated += 1

    data["items"] = kept
    if isinstance(data.get("meta"), dict):
        data["meta"]["post_filter_items"] = len(kept)
        data["meta"]["removed_threads_quality"] = removed_threads_quality

    NEWS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"[relevance] kept={len(kept)} removed_unrelated={removed_unrelated} "
        f"removed_threads_quality={removed_threads_quality}"
    )


if __name__ == "__main__":
    main()
