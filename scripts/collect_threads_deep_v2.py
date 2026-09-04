#!/usr/bin/env python3
"""Threads Deep Search v2.

Keeps the multi-engine strategy from collect_threads_deep.py, but fixes the
critical weakness of public Threads pages: individual post metadata is often
empty for logged-out visitors. v2 captures the visible text of each public
search-result card while the result is already visible in Threads search.
"""
import re
import shutil
import urllib.parse
from pathlib import Path

import collect_threads_deep as base


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
        context = browser.new_context(
            viewport={"width": 1280, "height": 1600},
            locale="zh-TW",
        )
        page = context.new_page()
        page.set_default_timeout(9000)

        for term in terms:
            for serp in ("recent", "default"):
                url = "https://www.threads.com/search/?" + urllib.parse.urlencode(
                    {"q": term, "serp_type": serp}
                )
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=16000)
                    page.wait_for_timeout(1300)
                    for _ in range(3):
                        page.mouse.wheel(0, 1700)
                        page.wait_for_timeout(450)

                    # Grab link + visible card text from the same DOM. We deliberately
                    # stop before ancestors become page-sized so the search box itself
                    # cannot make unrelated cards pass the relevance check.
                    cards = page.locator('a[href*="/post/"]').evaluate_all(
                        """els => els.map(a => {
                          let node = a;
                          let best = (a.innerText || '').trim();
                          for (let i = 0; i < 6; i++) {
                            node = node && node.parentElement;
                            if (!node) break;
                            const txt = (node.innerText || '').replace(/\\s+/g, ' ').trim();
                            if (txt.length >= 15 && txt.length <= 900 && txt.length > best.length) best = txt;
                            if (txt.length > 900) break;
                          }
                          return {href: a.href || '', text: best};
                        })"""
                    )

                    unique_this_page = set()
                    relevant_cards = 0
                    for card in cards:
                        link = base.canonical(card.get("href") or "")
                        if not base.is_threads_post(link) or link in unique_this_page:
                            continue
                        unique_this_page.add(link)
                        text = " ".join(str(card.get("text") or "").split())[:900]
                        if base.relevant(text):
                            relevant_cards += 1
                        old = candidates.get(link)
                        row = {
                            "url": link,
                            "snippet": text,
                            "publish_time": None,
                            "engine": f"threads_{serp}",
                        }
                        if not old or len(text) > len(old.get("snippet", "")):
                            candidates[link] = row

                    print(
                        f"[threads_deep_v2:threads:{serp}] term={term!r} "
                        f"links={len(unique_this_page)} relevant_cards={relevant_cards}"
                    )
                except Exception as exc:
                    print(f"[threads_deep_v2:threads:{serp}] term={term!r}: {exc}")

        browser.close()
    return candidates


def add_verified_v2(data, candidates, counts, limit=160):
    """Save only candidates whose search-result text itself proves NTUE relevance.

    This avoids requiring Threads' logged-out single-post page to expose OG metadata.
    Dates are left unknown rather than invented; discovered_at records collection time.
    """
    items = data["items"]
    existing = {base.canonical(x.get("url") or "") for x in items}
    added = 0

    ranked = sorted(
        candidates.values(),
        key=lambda x: (bool(base.relevant(x.get("snippet", ""))), len(x.get("snippet", ""))),
        reverse=True,
    )
    for info in ranked[:limit]:
        url = base.canonical(info.get("url") or "")
        if not base.is_threads_post(url) or url in existing:
            continue
        snippet = " ".join(str(info.get("snippet") or "").split())
        matched = base.relevant(snippet)
        if not matched or len(snippet) < 8:
            continue

        # Remove obvious Threads UI-only fragments without altering the post wording.
        cleaned = re.sub(r"^(Threads\s*)+", "", snippet, flags=re.I).strip()
        if not cleaned:
            cleaned = snippet

        m = re.search(r'/@([^/]+)/post/', url)
        author = m.group(1) if m else "Threads"
        items.append({
            "title": cleaned[:500],
            "url": url,
            "source": "Threads",
            "publisher": author,
            "publish_time": info.get("publish_time"),
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
