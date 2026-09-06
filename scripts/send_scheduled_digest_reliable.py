#!/usr/bin/env python3
"""Reliable scheduled bulletin dispatcher.

GitHub Actions cron runs can be delayed or skipped for a while.  The legacy
scheduler only considered a slot due for 60 minutes, which meant an 08:00
bulletin could be lost entirely if the next runner did not start until 09:01+
.

This wrapper changes only the scheduling policy:
- a slot becomes due once its local scheduled time has passed;
- it stays due for the rest of that local calendar day until delivery succeeds;
- email-state.json remains the idempotency guard, so a successful slot is sent
  at most once per day;
- missed slots from previous calendar days are never sent late on a new day.

The existing website-identical PDF renderer and Brevo sender are imported and
left unchanged.
"""
from datetime import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import send_scheduled_digest as digest  # noqa: E402
import send_scheduled_digest_with_ai  # noqa: F401,E402  # applies AI/PDF/Brevo monkeypatches


def reliable_due_slots(settings, state, now):
    if not settings.get("email_enabled"):
        return []

    sent = state.setdefault("last_sent", {})
    slots = []
    today = now.date().isoformat()

    for slot in settings.get("schedules", []):
        try:
            hh, mm = map(int, str(slot).split(":"))
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                continue
            target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        except Exception:
            continue

        key = f"{today}@{slot}"
        # No upper lateness limit within the same calendar day.  A delayed
        # GitHub runner will therefore catch up the slot instead of losing it.
        if now >= target and sent.get(slot) != key:
            slots.append((slot, key))

    # If multiple slots were missed, send them in chronological order.
    slots.sort(key=lambda item: item[0])
    return slots


digest.due_slots = reliable_due_slots


if __name__ == "__main__":
    digest.main()
