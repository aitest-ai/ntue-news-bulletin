#!/usr/bin/env python3
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import send_scheduled_digest_with_ai as ai  # noqa: E402
from taiwan_work_calendar import office_day_info  # noqa: E402

# The AI module applies the current production email sender monkey patches.
digest = ai.digest

DATA_DIR = ROOT / "frontend" / "public" / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"
STATE_FILE = DATA_DIR / "email-state.json"
NEWS_FILE = DATA_DIR / "news.json"
TAIPEI = timezone(timedelta(hours=8))
TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_profiles(settings):
    raw = settings.get("delivery_profiles")
    profiles = []
    if isinstance(raw, list):
        for index, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            profile_id = str(item.get("id") or f"profile-{index + 1}").strip()
            time_value = str(item.get("time") or "").strip()
            recipients = [str(x).strip() for x in item.get("recipients", []) if str(x).strip()]
            if not TIME_RE.match(time_value):
                continue
            profiles.append({
                "id": profile_id,
                "name": str(item.get("name") or f"推送任務 {index + 1}").strip(),
                "enabled": bool(item.get("enabled", True)),
                "time": time_value,
                "report_days": max(1, min(int(item.get("report_days") or 1), 30)),
                "include_latest_items": max(5, min(int(item.get("include_latest_items") or 20), 100)),
                "recipients": recipients,
                "subject_prefix": str(item.get("subject_prefix") or settings.get("subject_prefix") or "【國北教大輿情快報】").strip(),
                "sender_name": str(item.get("sender_name") or "").strip(),
                "sender_email": str(item.get("sender_email") or "").strip(),
                "exclude_holidays": bool(item.get("exclude_holidays", False)),
                "channel": "email",
            })
        return profiles

    recipients = [str(x).strip() for x in settings.get("recipients", []) if str(x).strip()]
    for index, slot in enumerate(settings.get("schedules", [])):
        slot = str(slot).strip()
        if not TIME_RE.match(slot):
            continue
        profiles.append({
            "id": f"legacy-{slot.replace(':', '')}-{index}",
            "name": f"{slot} 電子報",
            "enabled": bool(settings.get("email_enabled", True)),
            "time": slot,
            "report_days": max(1, min(int(settings.get("report_days") or 1), 30)),
            "include_latest_items": max(5, min(int(settings.get("include_latest_items") or 20), 100)),
            "recipients": recipients,
            "subject_prefix": str(settings.get("subject_prefix") or "【國北教大輿情快報】").strip(),
            "sender_name": "",
            "sender_email": "",
            "exclude_holidays": False,
            "channel": "email",
        })
    return profiles


def due_profiles(settings, state, now):
    sent = state.setdefault("last_sent_profiles", {})
    skipped = state.setdefault("last_skipped_profiles", {})
    due = []
    for profile in normalize_profiles(settings):
        if not profile["enabled"] or not profile["recipients"]:
            continue
        try:
            hh, mm = map(int, profile["time"].split(":"))
            target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        except Exception:
            continue
        key = f"{now.date().isoformat()}@{profile['time']}"
        if now < target or sent.get(profile["id"]) == key or skipped.get(profile["id"]) == key:
            continue

        if profile.get("exclude_holidays"):
            info = office_day_info(now.date())
            if info.get("is_holiday"):
                skipped[profile["id"]] = key
                holiday_name = info.get("name") or info.get("category") or "休假日"
                print(
                    f"[profiles] skip holiday id={profile['id']} key={key} "
                    f"holiday={holiday_name!r} source={info.get('source')}"
                )
                continue
            if info.get("warning"):
                print(f"[profiles] holiday calendar fallback workday: {info.get('warning')}")

        due.append((profile, key))
    return due


def send_profile(profile, feed):
    previous_sender_name = os.environ.get("BREVO_SENDER_NAME")
    previous_sender_email = os.environ.get("BREVO_SENDER_EMAIL")
    try:
        if profile.get("sender_name"):
            os.environ["BREVO_SENDER_NAME"] = profile["sender_name"]
        if profile.get("sender_email"):
            os.environ["BREVO_SENDER_EMAIL"] = profile["sender_email"]

        run_settings = {
            "email_enabled": True,
            "recipients": profile["recipients"],
            "report_days": profile["report_days"],
            "include_latest_items": profile["include_latest_items"],
            "subject_prefix": profile["subject_prefix"],
        }
        print(
            f"[profiles] sending id={profile['id']} name={profile['name']!r} "
            f"time={profile['time']} days={profile['report_days']} recipients={len(profile['recipients'])}"
        )
        try:
            return bool(digest.build_and_send(run_settings, feed, profile["time"]))
        except Exception as exc:
            print(f"[profiles] delivery aborted id={profile['id']}: {exc}")
            return False
    finally:
        if previous_sender_name is None:
            os.environ.pop("BREVO_SENDER_NAME", None)
        else:
            os.environ["BREVO_SENDER_NAME"] = previous_sender_name
        if previous_sender_email is None:
            os.environ.pop("BREVO_SENDER_EMAIL", None)
        else:
            os.environ["BREVO_SENDER_EMAIL"] = previous_sender_email


def main():
    settings = load_json(SETTINGS_FILE, {})
    state = load_json(STATE_FILE, {"last_sent": {}, "last_sent_profiles": {}, "last_skipped_profiles": {}})
    feed = load_json(NEWS_FILE, {"items": []})
    now = datetime.now(TAIPEI)
    before = json.dumps(state, ensure_ascii=False, sort_keys=True)
    due = due_profiles(settings, state, now)
    after = json.dumps(state, ensure_ascii=False, sort_keys=True)
    if before != after:
        save_json(STATE_FILE, state)

    if "--is-due" in sys.argv:
        raise SystemExit(0 if due else 1)

    if not due:
        print("[profiles] no delivery profile due")
        return 0

    failures = 0
    for profile, key in due:
        if send_profile(profile, feed):
            state.setdefault("last_sent_profiles", {})[profile["id"]] = key
            save_json(STATE_FILE, state)
            print(f"[profiles] delivered id={profile['id']} key={key}")
        else:
            failures += 1
            print(f"[profiles] delivery failed id={profile['id']}; will retry on next guard wake")

    if failures:
        print(f"[profiles] {failures}/{len(due)} due profile(s) failed")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
