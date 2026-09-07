#!/usr/bin/env python3
"""Threads Deep Search v3 quality gate.

Rules:
1. A Threads post must have a verifiable publication time before it can enter
   the feed. Unknown-date posts are rejected rather than treated as current.
2. Very old Threads posts are removed from the active monitoring feed.
3. Titles are derived from actual post text, never just the account/header row.
4. Direct post metadata is used to recover missing dates and body text when the
   public search card is incomplete.
"""
import html as html_lib
import re
import shutil
import urllib.parse
from datetime import datetime, timedelta, timezone

import collect_threads_deep as base

MAX_THREADS_AGE_DAYS = 45

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9,
    "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

SCHOOL_ONLY = {
    "國北教大", "北教大", "國北教", "國北", "ntue",
    "國立臺北教育大學", "國立台北教育大學", "臺北教育大學", "台北教育大學",
}


def post_url(url):
    """Normalize /media and other child links to one canonical Threads post URL."""
    raw = base.canonical(url)
    m = re.match(r"(https://www\.threads\.com/@[^/]+/post/[A-Za-z0-9_-]+)", raw, re.I)
    return m.group(1) if m else raw


def _iso(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(base.TAIPEI).isoformat()


def parse_visible_time(value, text=""):
    """Parse only timestamps that are actually exposed by Threads/search metadata."""
    raw = str(value or "").strip()
    if raw:
        try:
            return _iso(datetime.fromisoformat(raw.replace("Z", "+00:00")))
        except Exception:
            pass

    s = " ".join(str(text or "").split())

    m = re.search(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b", s)
    if m:
        try:
            return datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3)),
                12, 0, tzinfo=base.TAIPEI
            ).isoformat()
        except Exception:
            pass

    m = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+"
        r"(\d{1,2}),\s*(20\d{2})\b",
        s,
        re.I,
    )
    if m:
        try:
            month = MONTHS[m.group(1).lower()]
            return datetime(int(m.group(3)), month, int(m.group(2)), 12, 0, tzinfo=base.TAIPEI).isoformat()
        except Exception:
            pass

    m = re.search(r"(?<!\d)(\d{1,2})月(\d{1,2})日", s)
    if m:
        try:
            now = base.NOW()
            candidate = datetime(now.year, int(m.group(1)), int(m.group(2)), 12, 0, tzinfo=base.TAIPEI)
            if candidate > now + timedelta(days=2):
                candidate = candidate.replace(year=now.year - 1)
            return candidate.isoformat()
        except Exception:
            pass

    now = base.NOW()
    relative_patterns = [
        (r"(?<!\d)(\d{1,3})\s*週(?:前)?", "weeks"),
        (r"(?<!\d)(\d{1,3})\s*天(?:前)?", "days"),
        (r"(?<!\d)(\d{1,3})\s*小時(?:前)?", "hours"),
        (r"(?<!\d)(\d{1,3})\s*分鐘(?:前)?", "minutes"),
    ]
    for pat, unit in relative_patterns:
        m = re.search(pat, s)
        if not m:
            continue
        n = int(m.group(1))
        if unit == "weeks":
            return (now - timedelta(weeks=n)).isoformat()
        if unit == "days":
            return (now - timedelta(days=n)).isoformat()
        if unit == "hours":
            return (now - timedelta(hours=n)).isoformat()
        return (now - timedelta(minutes=n)).isoformat()
    return None


def date_is_fresh(value):
    """Reject unknown, future, or stale Threads timestamps."""
    if not value:
        return False
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=base.TAIPEI)
        dt = dt.astimezone(base.TAIPEI)
    except Exception:
        return False
    now = base.NOW()
    return now - timedelta(days=MAX_THREADS_AGE_DAYS) <= dt <= now + timedelta(days=1)


def author_from_url(url):
    m = re.search(r"/@([^/]+)/post/", str(url or ""))
    return m.group(1) if m else "Threads"


def clean_post_body(text, author=""):
    """Remove Threads/search UI chrome and keep readable post content."""
    s = html_lib.unescape(str(text or ""))
    s = s.replace("\u200b", " ").replace("\xa0", " ")
    s = " ".join(s.split())
    if not s:
        return ""

    for marker in (
        "Log in to see more replies", "Log in to see more", "登入以查看",
        "查看更多回覆", "View more replies",
    ):
        pos = s.lower().find(marker.lower())
        if pos >= 0:
            s = s[:pos].strip()

    s = re.sub(r"^(?:Threads\s*)+", "", s, flags=re.I).strip()
    if author:
        s = re.sub(rf"^\s*@?{re.escape(author)}\b[\s·•:：\-–—]*", "", s, flags=re.I).strip()

    s = re.sub(r"^\s*@[\w.]+\s*", "", s)
    s = re.sub(r"\b\d+\s+Replies\b", " ", s, flags=re.I)
    s = re.sub(r"\b\d+\s+repl(?:y|ies)\b", " ", s, flags=re.I)
    s = re.sub(r"\b\d+\s*(?:個)?回覆\b", " ", s)

    s = re.sub(r"\b20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}\b", " ", s)
    s = re.sub(
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+\d{1,2},\s*20\d{2}"
        r"(?:\s+at\s+\d{1,2}:\d{2}\s*(?:AM|PM)?)?",
        " ",
        s,
        flags=re.I,
    )
    s = re.sub(r"(?<!\d)\d{1,3}\s*(?:週|天|小時|分鐘)(?:前)?(?!\w)", " ", s)
    s = re.sub(r"\s*翻譯(?:\s+[\d,]+){1,8}\s*$", "", s)
    s = re.sub(r"(?:\s+[\d,]+){3,8}\s*$", "", s)
    s = " ".join(s.split()).strip(" ·•|—–-:：")

    clauses = re.split(r"(?<=[。！？!?])\s+", s)
    seen, unique = set(), []
    for clause in clauses:
        key = re.sub(r"\W+", "", clause).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(clause.strip())
    return " ".join(unique).strip()


def _metadata_only(text, author=""):
    """Detect cards that contain only username/school/time and no post body."""
    s = clean_post_body(text, author)
    n = base.norm(s)
    for token in SCHOOL_ONLY:
        n = n.replace(base.norm(token), " ")
    n = re.sub(r"[\W_]+", "", n)
    return len(n) < 6


def topic_title(text, author="", matched=""):
    """Create a concise, human-readable Threads headline from the post body."""
    body = clean_post_body(text, author)
    if not body:
        return ""

    body = re.sub(
        r"^(?:國立[臺台]北教育大學|[臺台]北教育大學|國北教大|北教大|國北教|NTUE)"
        r"\s*[|｜·•:：\-–—]+\s*",
        "",
        body,
        flags=re.I,
    ).strip()

    clauses = [x.strip() for x in re.split(r"(?<=[。！？!?])\s+|[\n\r]+", body) if x.strip()]
    meaningful = []
    for clause in clauses:
        n = base.norm(clause)
        stripped = n
        for token in SCHOOL_ONLY:
            stripped = stripped.replace(base.norm(token), " ")
        stripped = re.sub(r"[\W_]+", "", stripped)
        if len(stripped) >= 6:
            meaningful.append(clause)

    school_clauses = [
        clause for clause in meaningful
        if any(base.norm(token) in base.norm(clause) for token in SCHOOL_ONLY)
    ]
    chosen = school_clauses[0] if school_clauses else (meaningful[0] if meaningful else body)

    if len(chosen) < 28 and len(meaningful) > 1:
        try:
            idx = meaningful.index(chosen)
        except ValueError:
            idx = 0
        neighbor = meaningful[idx + 1] if idx + 1 < len(meaningful) else meaningful[0]
        if neighbor != chosen:
            chosen = f"{chosen} {neighbor}"

    chosen = " ".join(chosen.split()).strip(" ·•|—–-:：")
    if len(chosen) > 90:
        chosen = chosen[:88].rstrip("，,、；;：: ") + "…"
    return chosen


def _date_source(info, meta_pub=None):
    if meta_pub:
        return "post_metadata"
    if str(info.get("datetime") or "").strip():
        return "threads_datetime"
    snippet = str(info.get("snippet") or "")
    if re.search(r"\b20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}\b", snippet):
        return "visible_date"
    if re.search(r"\d{1,3}\s*(?:週|天|小時|分鐘)(?:前)?", snippet):
        return "relative_label"
    if info.get("publish_time"):
        return str(info.get("date_source") or info.get("engine") or "search_metadata")
    return ""


def collect_threads_browser_v2(terms):
    candidates = {}
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        print(f"[threads_deep_v3] playwright unavailable: {exc}")
        return candidates

    executable = (
        shutil.which("google-chrome") or shutil.which("google-chrome-stable")
        or shutil.which("chromium") or shutil.which("chromium-browser")
    )
    if not executable:
        print("[threads_deep_v3] system Chromium unavailable")
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
                          for (let i = 0; i < 10; i++) {
                            node = node && node.parentElement;
                            if (!node) break;
                            const txt = (node.innerText || '').replace(/\\s+/g, ' ').trim();
                            const hasTime = !!(node.querySelector && node.querySelector('time'));
                            if (txt.length >= 15 && txt.length <= 1400 &&
                                (txt.length > best.length || hasTime)) {
                              best = txt; bestNode = node;
                            }
                            if (txt.length > 1400) break;
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
                        text = " ".join(str(card.get("text") or "").split())[:1400]
                        if base.relevant(text):
                            relevant_cards += 1
                        visible_time = parse_visible_time(card.get("datetime"), text)
                        row = {
                            "url": link,
                            "snippet": text,
                            "publish_time": visible_time,
                            "datetime": card.get("datetime") or "",
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
                        f"[threads_deep_v3:threads:{serp}] term={term!r} "
                        f"links={len(unique_this_page)} relevant_cards={relevant_cards}"
                    )
                except Exception as exc:
                    print(f"[threads_deep_v3:threads:{serp}] term={term!r}: {exc}")

        browser.close()
    return candidates


def clean_existing_threads(data):
    """Normalize existing Threads rows and remove unknown/stale/header-only records."""
    best = {}
    others = []
    removed_unknown = removed_stale = removed_header = 0

    for item in data.get("items", []):
        if item.get("source") != "Threads":
            others.append(item)
            continue

        url = post_url(item.get("url") or "")
        if not base.is_threads_post(url):
            continue

        item = dict(item)
        item["url"] = url
        author = author_from_url(url)
        raw_text = str(item.get("snippet") or item.get("title") or "")
        pub = item.get("publish_time") or parse_visible_time("", raw_text)
        meta = ""
        meta_pub = None

        if not pub or _metadata_only(raw_text, author):
            meta, meta_pub = base.direct_post_meta(url)
            if meta_pub:
                pub = meta_pub
            if meta and (base.relevant(meta) or base.relevant(raw_text)):
                raw_text = meta

        if not pub:
            removed_unknown += 1
            continue
        if not date_is_fresh(pub):
            removed_stale += 1
            continue

        matched = base.relevant(raw_text) or item.get("keyword") or ""
        title = topic_title(raw_text, author, matched)
        if not title or _metadata_only(title, author):
            removed_header += 1
            continue

        item["publisher"] = author
        item["publish_time"] = pub
        item["date_verified"] = True
        item["date_source"] = "post_metadata" if meta_pub else str(item.get("date_source") or "existing_verified")
        item["snippet"] = clean_post_body(raw_text, author)[:1200]
        item["title"] = title
        old = best.get(url)
        score = (
            len(item.get("snippet") or ""),
            len(item.get("title") or ""),
        )
        old_score = (
            len((old or {}).get("snippet") or ""),
            len((old or {}).get("title") or ""),
        )
        if old is None or score > old_score:
            best[url] = item

    data["items"] = others + list(best.values())
    print(
        f"[threads_deep_v3:cleanup] kept={len(best)} "
        f"removed_unknown_date={removed_unknown} removed_stale={removed_stale} "
        f"removed_header_only={removed_header}"
    )
    return len(best)


def add_verified_v2(data, candidates, counts, limit=160):
    """Save only relevant Threads posts with a verified date and meaningful body."""
    clean_existing_threads(data)
    items = data["items"]
    existing = {post_url(x.get("url") or "") for x in items}
    added = 0
    skipped_date = skipped_body = 0

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

        author = author_from_url(url)
        pub = info.get("publish_time") or parse_visible_time(info.get("datetime"), snippet)
        text = snippet

        meta, meta_pub = base.direct_post_meta(url)
        if meta_pub:
            pub = meta_pub
        if meta and (base.relevant(meta) or matched):
            text = meta
            matched = base.relevant(meta) or matched

        if not pub or not date_is_fresh(pub):
            skipped_date += 1
            continue

        body = clean_post_body(text, author)
        title = topic_title(body, author, matched)
        if not title or _metadata_only(title, author):
            skipped_body += 1
            continue

        items.append({
            "title": title,
            "snippet": body[:1200],
            "url": url,
            "source": "Threads",
            "publisher": author,
            "publish_time": pub,
            "date_verified": True,
            "date_source": _date_source(info, meta_pub),
            "discovered_at": base.NOW().isoformat(),
            "keyword": matched,
            "task": "threads",
            "discovery": info.get("engine", "threads_deep_v3"),
        })
        existing.add(url)
        engine = info.get("engine", "threads_deep_v3")
        counts[engine] = counts.get(engine, 0) + 1
        added += 1
        if added % 10 == 0:
            base.checkpoint(data)

    base.checkpoint(data)
    print(
        f"[threads_deep_v3:add] added={added} skipped_no_verified_date={skipped_date} "
        f"skipped_no_meaningful_body={skipped_body}"
    )
    return added


base.collect_threads_browser = collect_threads_browser_v2
base.add_verified = add_verified_v2

if __name__ == "__main__":
    base.main()
