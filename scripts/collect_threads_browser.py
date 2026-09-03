#!/usr/bin/env python3
import html
import json
import re
import shutil
import subprocess
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

TAIPEI = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
NEWS_FILE = ROOT / "frontend" / "public" / "data" / "news.json"
KEYWORDS = ["國立臺北教育大學", "國北教大", "北教大", "NTUE", "National Taipei University of Education"]
RELEVANCE = ["國立臺北教育大學", "國立台北教育大學", "臺北教育大學", "台北教育大學", "國北教大", "國北教", "北教大", "國北", "NTUE", "National Taipei University of Education"]


def norm(s):
    return " ".join((s or "").replace("臺", "台").lower().split())


def relevant(text):
    n = norm(text)
    for term in RELEVANCE:
        if norm(term) in n:
            if "ntue" in n:
                return "NTUE"
            if "北教" in n or "國北" in n:
                return "國北教大"
            return "國立臺北教育大學"
    return None


def chrome_path():
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        p = shutil.which(name)
        if p:
            return p
    return None


def dump_dom(chrome, url):
    cmd = [
        chrome,
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-background-networking",
        "--disable-features=Translate,MediaRouter",
        "--window-size=1440,1600",
        "--virtual-time-budget=9000",
        "--dump-dom",
        url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "Chrome failed")[-500:])
    return proc.stdout


def extract_posts(dom, keyword):
    dom = html.unescape(dom).replace("\\/", "/").replace("\\u0026", "&")
    links = []
    seen = set()
    patterns = [
        r'https?://(?:www\.)?threads\.(?:com|net)/@[^"\'<>\s]+/post/[A-Za-z0-9_-]+',
        r'href=["\'](/@[^"\']+/post/[A-Za-z0-9_-]+)["\']',
    ]
    for idx, pattern in enumerate(patterns):
        for found in re.findall(pattern, dom, re.I):
            link = found if idx == 0 else "https://www.threads.com" + found
            link = link.split("?", 1)[0].replace("threads.net", "threads.com")
            if link not in seen:
                seen.add(link)
                links.append(link)
    return links[:80]


def page_meta(chrome, link):
    try:
        dom = dump_dom(chrome, link)
    except Exception:
        return "", None
    desc = ""
    for key in ("og:description", "twitter:description", "og:title"):
        pats = [
            rf'<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(key)}["\']',
        ]
        for pat in pats:
            m = re.search(pat, dom, re.I | re.S)
            if m:
                desc = html.unescape(m.group(1)).strip()
                break
        if desc:
            break
    dt = None
    taken = re.search(r'"taken_at"\s*:\s*(\d{10})', dom)
    if taken:
        try:
            dt = datetime.fromtimestamp(int(taken.group(1)), timezone.utc).astimezone(TAIPEI).isoformat()
        except Exception:
            pass
    return desc, dt


def main():
    chrome = chrome_path()
    if not chrome:
        print("[threads_browser] Chrome not available; skip")
        return
    if not NEWS_FILE.exists():
        print("[threads_browser] news.json missing; skip")
        return

    data = json.loads(NEWS_FILE.read_text(encoding="utf-8"))
    items = data.get("items", [])
    existing = {(x.get("url") or "").split("?", 1)[0] for x in items}
    candidates = []

    for keyword in KEYWORDS:
        urls = [
            "https://www.threads.com/search/?" + urllib.parse.urlencode({"q": keyword, "serp_type": "recent"}),
            "https://www.threads.com/search/?" + urllib.parse.urlencode({"q": keyword, "serp_type": "default"}),
        ]
        for url in urls:
            try:
                dom = dump_dom(chrome, url)
            except Exception as exc:
                print(f"[threads_browser:{keyword}] {exc}")
                continue
            for link in extract_posts(dom, keyword):
                if link not in existing and link not in candidates:
                    candidates.append(link)
        if len(candidates) >= 50:
            break

    added = 0
    for link in candidates[:50]:
        desc, publish_time = page_meta(chrome, link)
        matched = relevant(desc)
        if not matched:
            continue
        author = "Threads"
        m = re.search(r'/@([^/]+)/post/', link)
        if m:
            author = m.group(1)
        items.append({
            "title": desc[:300],
            "url": link,
            "source": "Threads",
            "publisher": author,
            "publish_time": publish_time,
            "discovered_at": datetime.now(TAIPEI).isoformat(),
            "keyword": matched,
            "task": "threads",
            "discovery": "threads_browser",
        })
        existing.add(link)
        added += 1

    # Keep previous Threads results and global newest-first ordering.
    def sort_key(x):
        return x.get("publish_time") or x.get("discovered_at") or ""
    items.sort(key=sort_key, reverse=True)
    data["items"] = items[:1500]
    for health in data.get("source_health", []):
        if health.get("task") == "threads":
            health.setdefault("engine_counts", {})["threads_browser"] = added
            health["count"] = sum(1 for x in data["items"] if x.get("source") == "Threads")
    data["summary"]["total"] = len(data["items"])
    NEWS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[threads_browser] candidates={len(candidates)} added={added}")


if __name__ == "__main__":
    main()
