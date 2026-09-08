#!/usr/bin/env python3
"""Taiwan government office work-calendar helper.

Uses the New Taipei City Government open-data mirror of the government
administrative office calendar. The dataset is updated annually and includes
weekends, national holidays, substitute holidays, adjusted holidays and
make-up workdays.

Network lookup is only needed near a configured delivery slot. A short-lived
workspace cache prevents duplicate requests inside the same Actions job. If the
government endpoint is temporarily unavailable and no cache exists, the helper
falls back to weekend detection so email reliability is not blocked by an
external dependency.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / ".cache"
CACHE_FILE = CACHE_DIR / "taiwan-government-work-calendar.json"
TAIPEI = timezone(timedelta(hours=8))
API_URL = "https://data.ntpc.gov.tw/api/datasets/308DCD75-6434-45BC-A95F-584DA4FED251/json"
CACHE_MAX_AGE = timedelta(hours=6)


def _date_key(day: date) -> str:
    return day.strftime("%Y%m%d")


def _normalize_rows(rows):
    result = {}
    if not isinstance(rows, list):
        return result
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("date") or "").strip()
        if len(key) != 8 or not key.isdigit():
            continue
        holiday_raw = str(row.get("isholiday") or "").strip().lower()
        is_holiday = holiday_raw in {"是", "true", "1", "2", "yes", "y"}
        result[key] = {
            "is_holiday": is_holiday,
            "name": str(row.get("name") or "").strip(),
            "category": str(row.get("holidaycategory") or "").strip(),
            "description": str(row.get("description") or "").strip(),
        }
    return result


def _read_cache():
    try:
        payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(str(payload.get("fetched_at") or "").replace("Z", "+00:00"))
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=TAIPEI)
        age = datetime.now(TAIPEI) - fetched_at.astimezone(TAIPEI)
        rows = payload.get("rows")
        if age <= CACHE_MAX_AGE and isinstance(rows, dict):
            return rows
    except Exception:
        pass
    return None


def _fetch_rows():
    req = urllib.request.Request(
        API_URL,
        headers={"User-Agent": "NTUE-Opinion-Bulletin/holiday-calendar"},
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        raw = json.loads(resp.read().decode("utf-8-sig"))
    rows = _normalize_rows(raw)
    if not rows:
        raise RuntimeError("government work-calendar returned no usable rows")
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(
            json.dumps(
                {"fetched_at": datetime.now(TAIPEI).isoformat(), "rows": rows},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass
    return rows


def office_day_info(day: date):
    """Return holiday status and provenance for a Taiwan local calendar date."""
    key = _date_key(day)
    rows = _read_cache()
    if not rows or key not in rows:
        try:
            rows = _fetch_rows()
        except Exception as exc:
            # Do not let an external calendar outage block the bulletin system.
            fallback_holiday = day.weekday() >= 5
            return {
                "is_holiday": fallback_holiday,
                "name": "週末" if fallback_holiday else "",
                "category": "fallback-weekend" if fallback_holiday else "fallback-workday",
                "source": "fallback",
                "warning": str(exc),
            }

    row = rows.get(key)
    if row is None:
        fallback_holiday = day.weekday() >= 5
        return {
            "is_holiday": fallback_holiday,
            "name": "週末" if fallback_holiday else "",
            "category": "fallback-weekend" if fallback_holiday else "fallback-workday",
            "source": "fallback",
            "warning": "date missing from government work-calendar",
        }

    return {**row, "source": "government-open-data"}


def is_office_holiday(day: date) -> bool:
    return bool(office_day_info(day).get("is_holiday"))
