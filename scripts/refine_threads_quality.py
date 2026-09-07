#!/usr/bin/env python3
"""Final Threads quality gate before AI/reporting.

This script intentionally prefers precision over recall:
- Only exact/traceable publication dates are accepted.
- Relative labels such as "3天" or search-engine index times are not enough.
- Feed titles are rewritten from the actual post body so account/header text is
  never shown as the discussion topic.
"""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEWS_FILE = ROOT / "frontend" / "public" / "data" / "news.json"
TAIPEI = timezone(timedelta(hours=8))
MAX_AGE_DAYS = 45
TRUSTED_DATE_SOURCES = {"threads_datetime", "post_metadata", "visible_date"}
SCHOOL_TERMS = [
    "國立臺北教育大學", "國立台北教育大學", "臺北教育大學", "台北教育大學",
    "國北教大", "北教大", "國北教", "NTUE", "國北",
]


def norm(value):
    return " ".join(str(value or "").replace("臺", "台").lower().split())


def valid_exact_date(item):
    if not item.get("date_verified"):
        return False
    if str(item.get("date_source") or "") not in TRUSTED_DATE_SOURCES:
        return False
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
    return now - timedelta(days=MAX_AGE_DAYS) <= dt <= now + timedelta(days=1)


def clean_body(value):
    s = " ".join(str(value or "").replace("\u200b", " ").split())
    for marker in ("Log in to see more replies", "Log in to see more", "登入以查看", "查看更多回覆"):
        pos = s.lower().find(marker.lower())
        if pos >= 0:
            s = s[:pos].strip()
    s = re.sub(r"\s*翻譯(?:\s+[\d,]+){1,8}\s*$", "", s)
    s = re.sub(r"(?:\s+[\d,]+){3,8}\s*$", "", s)
    s = re.sub(r"\b\d+\s+Replies\b", " ", s, flags=re.I)
    s = re.sub(r"\b\d+\s*(?:個)?回覆\b", " ", s)
    return " ".join(s.split()).strip(" ·•|—–-:：")


def meaningful(clause):
    probe = norm(clause)
    for term in SCHOOL_TERMS:
        probe = probe.replace(norm(term), " ")
    probe = re.sub(r"[\W_]+", "", probe)
    return len(probe) >= 6


def make_title(item):
    body = clean_body(item.get("snippet") or item.get("title") or "")
    if not body:
        return ""

    # Threads frequently returns one compressed line. Split on punctuation itself,
    # not only punctuation followed by spaces. This catches text such as
    # "……沒有錯，國立臺北教育大學...".
    clauses = [x.strip(" ，,、；;：:·•|—–-") for x in re.split(r"[。！？!?…]+", body) if x.strip()]
    useful = [x for x in clauses if meaningful(x)]
    relevant = [
        x for x in useful
        if any(norm(term) in norm(x) for term in SCHOOL_TERMS)
    ]
    chosen = relevant[0] if relevant else (useful[0] if useful else body)

    # If the selected clause is extremely short, attach one neighboring meaningful
    # clause to make the subject understandable without opening Threads.
    if len(chosen) < 24 and len(useful) > 1:
        try:
            idx = useful.index(chosen)
        except ValueError:
            idx = 0
        neighbor = useful[idx + 1] if idx + 1 < len(useful) else useful[0]
        if neighbor != chosen:
            chosen = f"{chosen}；{neighbor}"

    chosen = clean_body(chosen)
    if len(chosen) > 90:
        chosen = chosen[:88].rstrip("，,、；;：: ") + "…"
    return chosen


def main():
    data = json.loads(NEWS_FILE.read_text(encoding="utf-8"))
    kept = []
    removed_untrusted_date = 0
    removed_no_topic = 0
    rewritten = 0

    for item in data.get("items", []):
        if item.get("source") != "Threads" and item.get("task") != "threads":
            kept.append(item)
            continue

        if not valid_exact_date(item):
            removed_untrusted_date += 1
            continue

        new_title = make_title(item)
        if not new_title or not meaningful(new_title):
            removed_no_topic += 1
            continue

        row = dict(item)
        row["title"] = new_title
        row["snippet"] = clean_body(item.get("snippet") or item.get("title") or "")[:1200]
        row["date_verified"] = True
        row["title_generated_from_body"] = True
        kept.append(row)
        rewritten += 1

    data["items"] = kept
    if isinstance(data.get("meta"), dict):
        data["meta"]["threads_exact_date_gate_removed"] = removed_untrusted_date
        data["meta"]["threads_title_gate_removed"] = removed_no_topic

    NEWS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"[threads_quality] rewritten={rewritten} "
        f"removed_untrusted_date={removed_untrusted_date} removed_no_topic={removed_no_topic}"
    )


if __name__ == "__main__":
    main()
