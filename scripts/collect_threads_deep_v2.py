#!/usr/bin/env python3
"""Threads Deep Search v2.

Captures visible public Threads search-result cards, normalizes duplicate post
URLs, and preserves the card's visible timestamp so old posts do not leak into
short reporting windows merely because they were discovered today.
"""
import re
import shutil
import urllib.parse
from datetime import datetime, timedelta, timezone

import collect_threads_deep as base


def post_url(url):
    """Normalize /media and other child links to one canonical Threads post URL."""
    raw = base.canonical(url)
    m = re.match(r"(https://www\.threads\.com/@[^/]+/post/[A-Za-z0-9_-]+)", raw, re.I)
    return m.group(1) if m else raw


def parse_visible_time(value, text=""):
    """Prefer machine-readable datetime; otherwise parse only explicit visible time labels."""
    raw = str(value or "").strip()
    if raw:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(base.TAIPEI).isoformat()
        except Exception:
            pass

    s = " ".join(str(text or "").split())
    # Threads cards sometimes expose a calendar date directly.
    m = re.search(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b", s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), 12, 0, tzinfo=base.TAIPEI).isoformat()
        except Exception:
            pass

    now = base.NOW()
    relative_patterns = [
        (r"(?<!\d)(\d{1,3})\s*天(?:前)?", "days"),
        (r"(?<!\d)(\d{1,3})\s*小時(?:前)?", "hours"),
        (r"(?<!\d)(\d{1,3})\s*分鐘(?:前)?", "minutes"),
    ]
    for pat, unit in relative_patterns:
        m = re.search(pat, s)
        if not m:
            continue
        n = int(m.group(1))
        if unit == "days":
            return (now - timedelta(days=n)).isoformat()
        if unit == "hours":
            return (now - timedelta(hours=n)).isoformat()
        return (now - timedelta(minutes=n)).isoformat()
    return None


def collect_threads_browser_v2(terms):
    candidates = {}
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        print(f"[threads_deep_v2] playwright unavailable: {exc}")
        return candidates

    executable = (
        shutil.which("google-chrome") or shutil.which("google-chrome-stable")
        or shutil.which("chromium") or shutil.which("chromium-browser")
    )
    if not executable:
        print("[threads_deep_v2] system Chromium unavailable")
        return candidates

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=executable,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(viewport={"width": 1280, "height": 1600}, locale="zh-TW")
        page = context.new_page()
        page.set_default_timeout(9000)

        for term in terms:
            for serp in ("recent", "default"):
                url = "https://www.threads.com/search/?" + urllib.parse.urlencode({"q": term, "serp_type": serp})
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=16000)
                    page.wait_for_timeout(1300)
                    for _ in range(3):
                        page.mouse.wheel(0, 1700)
                        page.wait_for_timeout(450)

                    cards = page.locator('a[href*="/post/"]').evaluate_all(
                        """els => els.map(a => {
                          let node = a;
                          let best = (a.innerText || '').trim();
                          let bestNode = a;
                          for (let i = 0; i < 6; i++) {
                            node = node && node.parentElement;
                            if (!node) break;
                            const txt = (node.innerText || '').replace(/\\s+/g, ' ').trim();
                            if (txt.length >= 15 && txt.length <= 900 && txt.length > best.length) {
                              best = txt; bestNode = node;
                            }
                            if (txt.length > 900) break;
                          }
                          const time = (bestNode && bestNode.querySelector && bestNode.querySelector('time')) || null;
                          return {
                            href: a.href || '',
                            text: best,
                            datetime: time ? (time.getAttribute('datetime') || time.getAttribute('title') || '') : ''
                          };
                        })"""
                    )

                    unique_this_page = set()
                    relevant_cards = 0
                    for card in cards:
                        link = post_url(card.get("href") or "")
                        if not base.is_threads_post(link) or link in unique_this_page:
                            continue
                        unique_this_page.add(link)
                        text = " ".join(str(card.get("text") or "").split())[:900]
                        if base.relevant(text):
                            relevant_cards += 1
                        visible_time = parse_visible_time(card.get("datetime"), text)
                        row = {
                            "url": link,
                            "snippet": text,
                            "publish_time": visible_time,
                            "engine": f"threads_{serp}",
                        }
                        old = candidates.get(link)
                        if (
                            not old
                            or len(text) > len(old.get("snippet", ""))
                            or (visible_time and not old.get("publish_time"))
                        ):
                            candidates[link] = row

                    print(
                        f"[threads_deep_v2:threads:{serp}] term={term!r} "
                        f"links={len(unique_this_page)} relevant_cards={relevant_cards}"
                    )
                except Exception as exc:
                    print(f"[threads_deep_v2:threads:{serp}] term={term!r}: {exc}")

        browser.close()
    return candidates


def clean_existing_threads(data):
    """Normalize previously collected Threads rows, dedupe, and backfill visible dates from their titles."""
    best = {}
    others = []
    for item in data.get("items", []):
        if item.get("source") != "Threads":
            others.append(item)
            continue
        url = post_url(item.get("url") or "")
        if not base.is_threads_post(url):
            continue
        item = dict(item)
        item["url"] = url
        if not item.get("publish_time"):
            item["publish_time"] = parse_visible_time("", item.get("title") or "")
        old = best.get(url)
        score = (bool(item.get("publish_time")), len(str(item.get("title") or "")))
        old_score = (bool(old and old.get("publish_time")), len(str((old or {}).get("title") or "")))
        if old is None or score > old_score:
            best[url] = item
    data["items"] = others + list(best.values())
    return len(best)


def add_verified_v2(data, candidates, counts, limit=160):
    """Save only posts whose public search-card text itself proves NTUE relevance."""
    clean_existing_threads(data)
    items = data["items"]
    existing = {post_url(x.get("url") or "") for x in items}
    added = 0

    ranked = sorted(
        candidates.values(),
        key=lambda x: (
            bool(base.relevant(x.get("snippet", ""))),
            bool(x.get("publish_time")),
            len(x.get("snippet", "")),
        ),
        reverse=True,
    )
    for info in ranked[:limit]:
        url = post_url(info.get("url") or "")
        if not base.is_threads_post(url) or url in existing:
            continue
        snippet = " ".join(str(info.get("snippet") or "").split())
        matched = base.relevant(snippet)
        if not matched or len(snippet) < 8:
            continue

        cleaned = re.sub(r"^(Threads\s*)+", "", snippet, flags=re.I).strip() or snippet
        publish_time = info.get("publish_time") or parse_visible_time("", cleaned)
        m = re.search(r'/@([^/]+)/post/', url)
        author = m.group(1) if m else "Threads"
        items.append({
            "title": cleaned[:500],
            "url": url,
            "source": "Threads",
            "publisher": author,
            "publish_time": publish_time,
            "discovered_at": base.NOW().isoformat(),
            "keyword": matched,
            "task": "threads",
            "discovery": info.get("engine", "threads_deep_v2"),
        })
        existing.add(url)
        engine = info.get("engine", "threads_deep_v2")
        counts[engine] = counts.get(engine, 0) + 1
        added += 1
        if added % 10 == 0:
            base.checkpoint(data)

    base.checkpoint(data)
    return added


base.collect_threads_browser = collect_threads_browser_v2
base.add_verified = add_verified_v2

if __name__ == "__main__":
    base.main()
