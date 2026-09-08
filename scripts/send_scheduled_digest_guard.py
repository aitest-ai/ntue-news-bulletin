#!/usr/bin/env python3
"""Profile-aware pre-warmed delivery guard.

The collector and the mail scheduler are deliberately separated. This guard is
lightweight and may run frequently. When an enabled delivery profile is already
due, it dispatches immediately. When the next profile is close, it waits until
the exact local time and then delegates to send_delivery_profiles.py.

State is keyed by delivery-profile id in last_sent_profiles, matching the
settings UI and the production dispatcher. Holiday-skipped slots are recorded
separately so they are not retried later the same day.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from taiwan_work_calendar import office_day_info  # noqa: E402

DATA_DIR = ROOT / "frontend" / "public" / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"
STATE_FILE = DATA_DIR / "email-state.json"
TAIPEI = timezone(timedelta(hours=8))
TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
MAX_PREWARM_MINUTES = 20


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_profiles(settings):
    raw = settings.get("delivery_profiles")
    profiles = []
    if isinstance(raw, list):
        for index, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            profile_id = str(item.get("id") or f"profile-{index + 1}").strip()
            slot = str(item.get("time") or "").strip()
            recipients = [str(x).strip() for x in item.get("recipients", []) if str(x).strip()]
            if not profile_id or not TIME_RE.match(slot):
                continue
            profiles.append({
                "id": profile_id,
                "name": str(item.get("name") or f"推送任務 {index + 1}").strip(),
                "enabled": bool(item.get("enabled", True)),
                "time": slot,
                "recipients": recipients,
                "exclude_holidays": bool(item.get("exclude_holidays", False)),
            })
        return profiles

    recipients = [str(x).strip() for x in settings.get("recipients", []) if str(x).strip()]
    for index, raw_slot in enumerate(settings.get("schedules", [])):
        slot = str(raw_slot).strip()
        if TIME_RE.match(slot):
            profiles.append({
                "id": f"legacy-{slot.replace(':', '')}-{index}",
                "name": f"{slot} 電子報",
                "enabled": bool(settings.get("email_enabled", True)),
                "time": slot,
                "recipients": recipients,
                "exclude_holidays": False,
            })
    return profiles


def _holiday_candidate(target, profile, key, mode):
    if not profile.get("exclude_holidays"):
        return None
    info = office_day_info(target.date())
    if not info.get("is_holiday"):
        if info.get("warning"):
            print(f"[delivery-guard] holiday calendar fallback workday: {info.get('warning')}")
        return None
    return (target, profile, 0.0, key, "holiday_skip", info)


def candidate_for_profile(profile, sent, skipped, now):
    if not profile["enabled"] or not profile["recipients"]:
        return None

    hh, mm = map(int, profile["time"].split(":"))
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    today_key = f"{now.date().isoformat()}@{profile['time']}"
    recorded = sent.get(profile["id"])
    skipped_key = skipped.get(profile["id"])

    if recorded != today_key and skipped_key != today_key:
        if now >= target:
            holiday = _holiday_candidate(target, profile, today_key, "overdue")
            if holiday:
                return holiday
            return (target, profile, 0.0, today_key, "overdue", None)

        seconds = (target - now).total_seconds()
        if seconds <= MAX_PREWARM_MINUTES * 60:
            holiday = _holiday_candidate(target, profile, today_key, "prewarm")
            if holiday:
                return holiday
            return (target, profile, max(0.0, seconds), today_key, "prewarm", None)
        return None

    # Today's slot was already delivered or deliberately skipped. Near midnight,
    # a 00:xx profile can be pre-warmed across the date boundary for tomorrow.
    tomorrow = now + timedelta(days=1)
    tomorrow_target = tomorrow.replace(hour=hh, minute=mm, second=0, microsecond=0)
    tomorrow_key = f"{tomorrow.date().isoformat()}@{profile['time']}"
    if sent.get(profile["id"]) == tomorrow_key or skipped.get(profile["id"]) == tomorrow_key:
        return None
    seconds = (tomorrow_target - now).total_seconds()
    if seconds <= MAX_PREWARM_MINUTES * 60:
        holiday = _holiday_candidate(tomorrow_target, profile, tomorrow_key, "prewarm")
        if holiday:
            return holiday
        return (tomorrow_target, profile, max(0.0, seconds), tomorrow_key, "prewarm", None)
    return None


def find_action(now: datetime):
    settings = load_json(SETTINGS_FILE, {})
    state = load_json(STATE_FILE, {"last_sent_profiles": {}, "last_skipped_profiles": {}})
    sent = state.get("last_sent_profiles", {}) if isinstance(state, dict) else {}
    skipped = state.get("last_skipped_profiles", {}) if isinstance(state, dict) else {}
    if not isinstance(sent, dict):
        sent = {}
    if not isinstance(skipped, dict):
        skipped = {}

    candidates = []
    for profile in normalize_profiles(settings):
        candidate = candidate_for_profile(profile, sent, skipped, now)
        if candidate:
            candidates.append(candidate)

    if not candidates:
        return None

    # Holiday skips and overdue deliveries should be resolved immediately.
    priority = {"holiday_skip": 0, "overdue": 1, "prewarm": 2}
    candidates.sort(key=lambda row: (priority.get(row[4], 9), row[0]))
    return candidates[0]


def main():
    check_only = "--check" in sys.argv
    now = datetime.now(TAIPEI)
    action = find_action(now)
    if not action:
        print("[delivery-guard] no due or near-due delivery profile")
        return 1 if check_only else 0

    target, profile, wait_seconds, key, mode, holiday_info = action
    print(
        f"[delivery-guard] action={mode} id={profile['id']} name={profile['name']!r} "
        f"slot={profile['time']} key={key} wait={int(wait_seconds)}s"
    )
    if check_only:
        return 0

    if mode == "holiday_skip":
        state = load_json(STATE_FILE, {"last_sent": {}, "last_sent_profiles": {}, "last_skipped_profiles": {}})
        skipped = state.setdefault("last_skipped_profiles", {})
        skipped[profile["id"]] = key
        save_json(STATE_FILE, state)
        holiday_name = (holiday_info or {}).get("name") or (holiday_info or {}).get("category") or "休假日"
        source = (holiday_info or {}).get("source") or "calendar"
        print(
            f"[delivery-guard] skipped holiday id={profile['id']} key={key} "
            f"holiday={holiday_name!r} source={source}"
        )
        return 0

    if wait_seconds > 0:
        time.sleep(wait_seconds)

    # The dispatcher re-reads settings/state after the wait, so another runner
    # that delivered first will not cause a duplicate.
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "send_delivery_profiles.py")],
        cwd=str(ROOT),
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
