#!/usr/bin/env python3
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
NEWS_FILE = ROOT / "frontend" / "public" / "data" / "news.json"
SOCIAL = {"Dcard", "PTT", "Threads", "Instagram"}
TERMS = [
    "國立臺北教育大學", "國立台北教育大學", "臺北教育大學", "台北教育大學",
    "國北教大", "國北教", "北教大", "ntue", "national taipei university of education",
]


def norm(value):
    return " ".join(str(value or "").replace("臺", "台").lower().split())


def keep(item):
    source = str(item.get("source") or "")
    task = str(item.get("task") or "")
    url = str(item.get("url") or "")
    host = (urlparse(url).netloc or "").lower()

    # Social collectors already perform relevance checks using search result text/snippets.
    if source in SOCIAL or task in {"dcard", "ptt", "instagram", "threads"}:
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
    kept = [item for item in items if keep(item)]
    removed = len(items) - len(kept)
    data["items"] = kept
    # Preserve existing metadata, but make the post-filter count explicit when present.
    if isinstance(data.get("meta"), dict):
        data["meta"]["post_filter_items"] = len(kept)
    NEWS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[relevance] kept={len(kept)} removed_unrelated={removed}")


if __name__ == "__main__":
    main()
