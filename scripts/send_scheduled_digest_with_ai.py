#!/usr/bin/env python3
"""Compatibility shim for the profile dispatcher.

Scheduled bulletins are now HTML-only. AI summarization and Brevo delivery live
in send_scheduled_digest.py; there is no browser/PDF monkeypatch anymore.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import send_scheduled_digest as digest  # noqa: E402


if __name__ == "__main__":
    digest.main()
