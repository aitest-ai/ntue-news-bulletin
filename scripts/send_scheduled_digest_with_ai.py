#!/usr/bin/env python3
"""Compatibility shim for the profile dispatcher.

Scheduled bulletins are HTML-only and mirror the dashboard's news/social feed
cards. Source URLs are prepared by the collector quality pipeline.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import send_email_brief_v2 as digest  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(0)
