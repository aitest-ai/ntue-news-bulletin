#!/usr/bin/env python3
"""Pre-warmed delivery guard for time-sensitive bulletin sends.

This process may start shortly before a configured local-time slot. It waits
until the exact slot, re-reads repository-local settings/state, then delegates
to the reliable dispatcher. If it starts after the slot, it sends immediately
when that slot has not yet been recorded as successful today.

The guard intentionally does not collect news or Threads. Delivery is kept
lightweight and independent from the slower collector workflow.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "frontend" / "public" / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"
STATE_FILE = DATA_DIR / "email-state.json"
TAIPEI = timezone(timedelta(hours=8))
MAX_PREWARM_MINUTES = 20


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def find_action(now: datetime):
    settings = load_json(SETTINGS_FILE, {})
    state = load_json(STATE_FILE, {"last_sent": {}})
    if not settings.get("email_enabled"):
        return None

    sent = state.get("last_sent", {}) if isinstance(state, dict) else {}
    candidates = []
    today = now.date().isoformat()

    for raw_slot in settings.get("schedules", []):
        slot = str(raw_slot).strip()
        try:
            hh, mm = map(int, slot.split(":"))
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                continue
        except Exception:
            continue
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        key = f"{today}@{slot}"
        if sent.get(slot) == key:
            continue
        seconds = (target - now).total_seconds()
        if seconds <= MAX_PREWARM_MINUTES * 60:
            # Negative means the slot is already late and should be caught up now.
            candidates.append((target, slot, max(0.0, seconds)))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0]


def main():
    now = datetime.now(TAIPEI)
    action = find_action(now)
    if not action:
        print("[delivery-guard] no due or near-due slot")
        return 0

    target, slot, wait_seconds = action
    if wait_seconds > 0:
        print(
            f"[delivery-guard] pre-warmed for {slot}; waiting {int(wait_seconds)}s "
            f"until {target.isoformat()}"
        )
        time.sleep(wait_seconds)
    else:
        print(f"[delivery-guard] {slot} already due; attempting same-day catch-up now")

    # Re-read settings/state inside the reliable dispatcher after waiting. This
    # preserves idempotency if another runner delivered while this guard slept.
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "send_scheduled_digest_reliable.py")],
        cwd=str(ROOT),
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
