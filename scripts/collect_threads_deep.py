#!/usr/bin/env python3
"""Deep public Threads discovery for NTUE opinion monitoring.

Uses multiple independent public discovery paths:
1. Threads web search (recent + default) in one long-lived Chromium session.
2. Bing RSS / HTML search.
3. DuckDuckGo HTML search.
4. Yahoo Taiwan search.
5. Direct post metadata verification before saving.

No login, private API, session cookie, or access-control bypass is used.
"""
import concurrent.futures
import email.utils
import html
import json
import re
import shutil
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

TAIPEI = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
NEWS_FILE = ROOT / "frontend" / "public" / "data" / "news.json"

# Always search these because they are the highest-value aliases actually used by students.
CORE_TERMS = [
    "國北教大", "北教大", "國北教", "國立臺北教育大學",
    "臺北教育大學", "台北教育大學", "NTUE",
]

# Rotated expansion terms catch casual / hashtag / campus-topic wording.
EXPANSION_GROUPS = [
    ["國北", "#國北教大", "#北教大", "#NTUE", "國北 教授", "國北 老師"],
    ["國北 學生", "國北 校園", "國北 宿舍", "國北 選課", "北教大 宿舍", "北教大 選課"],
    ["國北 課程", "國北 社團", "國北 系所", "國北 實習", "北教大 學生", "北教大 校園"],
]

RELEVANCE = [
    "國立臺北教育大學", "國立台北教育大學", "臺北教育大學", "台北教育大學",
    "國北教大", "國北教", "北教大", "國北", "NTUE",
]

THREADS_HOSTS = {"threads.com", "www.threads.com", "threads.net", "www.threads.net"}
NOW = lambda: datetime.now(TAIPEI)


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


def canonical(url):
    if not url:
        return ""
    url = html.unescape(str(url)).replace("\\/", "/").replace("threads.net", "threads.com")
    if url.startswith("//"):
        url = "https:" + url
    try:
        p = urlparse(url)
        if p.netloc.lower() in THREADS_HOSTS:
            return f"https://www.threads.com{p.path}".rstrip("/")
    except Exception:
        pass
    return url.split("?", 1)[0].split("#", 1)[0]


def is_threads_post(url):
    try:
        p = urlparse(canonical(url))
        return p.netloc.lower() in THREADS_HOSTS and "/@" in p.path and "/post/" in p.path
    except Exception:
        return False


def extract_post_links(text):
    if not text:
        return []
    text = html.unescape(text).replace("\\/", "/").replace("\\u0026", "&")
    out, seen = [], set()
    patterns = [
        r'https?://(?:www\.)?threads\.(?:com|net)/@[^"\'<>\s?]+/post/[A-Za-z0-9_-]+',
        r'href=["\'](/@[^"\']+/post/[A-Za-z0-9_-]+)["\']',
    ]
    for pat in patterns:
        for raw in re.findall(pat, text, re.I):
            link = canonical("https://www.threads.com" + raw if raw.startswith("/") else raw)
            if is_threads_post(link) and link not in seen:
                seen.add(link)
                out.append(link)
    return out


def request_text(url, timeout=10):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/150 Safari/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def parse_rfc822(value):
    try:
        dt = email.utils.parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TAIPEI).isoformat()
    except Exception:
        return None


def search_bing_rss(query):
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query, "format": "rss", "setlang": "zh-Hant", "mkt": "zh-TW"})
    root = ET.fromstring(request_text(url))
    rows = []
    for node in root.findall(".//item")[:80]:
        link = canonical(node.findtext("link") or "")
        if not is_threads_post(link):
            continue
        rows.append({
            "url": link,
            "snippet": " ".join([(node.findtext("title") or "").strip(), (node.findtext("description") or "").strip()]),
            "publish_time": parse_rfc822(node.findtext("pubDate") or ""),
            "engine": "bing_rss",
        })
    return rows


def search_bing_html(query):
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query, "count": 50, "setlang": "zh-hant"})
    page = request_text(url)
    rows = []
    for link in extract_post_links(page):
        rows.append({"url": link, "snippet": "", "publish_time": None, "engine": "bing_html"})
    return rows


def search_ddg(query):
    page = request_text("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query))
    rows = []
    for m in re.finditer(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, re.I | re.S):
        href = html.unescape(m.group(1))
        if "uddg=" in href:
            try:
                href = urllib.parse.unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
            except Exception:
                pass
        link = canonical(href)
        if not is_threads_post(link):
            continue
        title = html.unescape(re.sub(r"<[^>]+>", " ", m.group(2))).strip()
        rows.append({"url": link, "snippet": title, "publish_time": None, "engine": "duckduckgo"})
    return rows[:60]


def search_yahoo(query):
    page = request_text("https://tw.search.yahoo.com/search?p=" + urllib.parse.quote(query))
    rows = []
    # Yahoo wraps some outbound URLs; extract both wrapped and direct Threads links from the page.
    for link in extract_post_links(page):
        rows.append({"url": link, "snippet": "", "publish_time": None, "engine": "yahoo"})
    for m in re.finditer(r'/RU=([^/]+)/', page):
        try:
            link = canonical(urllib.parse.unquote(m.group(1)))
        except Exception:
            continue
        if is_threads_post(link):
            rows.append({"url": link, "snippet": "", "publish_time": None, "engine": "yahoo"})
    return rows[:60]


def metadata_from_html(page):
    desc = ""
    for key in ("og:description", "twitter:description", "og:title", "twitter:title"):
        for pat in [
            rf'<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(key)}["\']',
        ]:
            m = re.search(pat, page, re.I | re.S)
            if m:
                desc = html.unescape(m.group(1)).strip()
                break
        if desc:
            break

    dt = None
    timestamp_patterns = [
        r'"taken_at"\s*:\s*(\d{10})',
        r'"taken_at_timestamp"\s*:\s*(\d{10})',
    ]
    for pat in timestamp_patterns:
        m = re.search(pat, page)
        if m:
            try:
                dt = datetime.fromtimestamp(int(m.group(1)), timezone.utc).astimezone(TAIPEI).isoformat()
            except Exception:
                pass
            break
    if not dt:
        m = re.search(r'<time[^>]+datetime=["\']([^"\']+)', page, re.I)
        if not m:
            m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', page)
        if m:
            try:
                parsed = datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
                dt = parsed.astimezone(TAIPEI).isoformat()
            except Exception:
                pass
    return desc, dt


def direct_post_meta(url):
    try:
        return metadata_from_html(request_text(url, timeout=9))
    except Exception:
        return "", None


def load_data():
    data = json.loads(NEWS_FILE.read_text(encoding="utf-8"))
    data.setdefault("items", [])
    return data


def checkpoint(data):
    data["items"].sort(key=lambda x: x.get("publish_time") or x.get("discovered_at") or "", reverse=True)
    data["items"] = data["items"][:2200]
    data.setdefault("summary", {})["total"] = len(data["items"])
    NEWS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def add_verified(data, candidates, counts, limit=120):
    items = data["items"]
    existing = {canonical(x.get("url") or "") for x in items}
    added = 0
    # Prefer candidates whose search snippet already looks relevant.
    ranked = sorted(candidates.values(), key=lambda x: bool(relevant(x.get("snippet", ""))), reverse=True)
    for info in ranked[:limit]:
        url = canonical(info["url"])
        if not is_threads_post(url) or url in existing:
            continue
        snippet = info.get("snippet", "")
        matched = relevant(snippet)
        text, pub = "", info.get("publish_time")
        # Always inspect direct post metadata when possible; this improves title quality and date accuracy.
        meta, meta_pub = direct_post_meta(url)
        if meta:
            text = meta
            matched = matched or relevant(meta)
        if meta_pub:
            pub = meta_pub
        if not matched:
            continue
        if not text:
            text = snippet
        if not text:
            continue
        m = re.search(r'/@([^/]+)/post/', url)
        author = m.group(1) if m else "Threads"
        items.append({
            "title": text[:500],
            "url": url,
            "source": "Threads",
            "publisher": author,
            "publish_time": pub,
            "discovered_at": NOW().isoformat(),
            "keyword": matched,
            "task": "threads",
            "discovery": info.get("engine", "threads_deep"),
        })
        existing.add(url)
        counts[info.get("engine", "threads_deep")] = counts.get(info.get("engine", "threads_deep"), 0) + 1
        added += 1
        if added % 5 == 0:
            checkpoint(data)
    checkpoint(data)
    return added


def collect_search_engines(terms):
    candidates = {}
    # Search engines understand site: filters better than raw phrase-only queries.
    queries = []
    for term in terms:
        queries.extend([
            f'site:threads.com/@ "{term}"',
            f'site:threads.com "{term}"',
        ])
    jobs = []
    functions = [search_bing_rss, search_bing_html, search_ddg, search_yahoo]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for query in queries:
            for fn in functions:
                jobs.append((query, fn.__name__, pool.submit(fn, query)))
        for query, name, fut in jobs:
            try:
                rows = fut.result(timeout=16)
            except Exception as exc:
                print(f"[threads_deep:{name}] {query!r}: {exc}")
                continue
            for row in rows:
                url = canonical(row.get("url"))
                if not is_threads_post(url):
                    continue
                old = candidates.get(url)
                if old and not old.get("snippet") and row.get("snippet"):
                    old["snippet"] = row["snippet"]
                elif not old:
                    candidates[url] = row
    return candidates


def collect_threads_browser(terms):
    candidates = {}
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        print(f"[threads_deep] playwright unavailable: {exc}")
        return candidates

    executable = (
        shutil.which("google-chrome") or shutil.which("google-chrome-stable")
        or shutil.which("chromium") or shutil.which("chromium-browser")
    )
    if not executable:
        print("[threads_deep] system Chromium unavailable")
        return candidates

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=executable, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(viewport={"width": 1280, "height": 1400}, locale="zh-TW")
        page = context.new_page()
        page.set_default_timeout(8000)
        for term in terms:
            for serp in ("recent", "default"):
                url = "https://www.threads.com/search/?" + urllib.parse.urlencode({"q": term, "serp_type": serp})
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(1200)
                    # A few scrolls expose more public results without needing login.
                    for _ in range(2):
                        page.mouse.wheel(0, 1800)
                        page.wait_for_timeout(450)
                    dom = page.content()
                    links = extract_post_links(dom)
                    print(f"[threads_deep:threads:{serp}] term={term!r} links={len(links)}")
                    for link in links:
                        candidates.setdefault(link, {"url": link, "snippet": "", "publish_time": None, "engine": f"threads_{serp}"})
                except Exception as exc:
                    print(f"[threads_deep:threads:{serp}] term={term!r}: {exc}")
        browser.close()
    return candidates


def main():
    if not NEWS_FILE.exists():
        print("[threads_deep] news.json missing")
        return

    slot = (NOW().minute // 10) % len(EXPANSION_GROUPS)
    expansion = EXPANSION_GROUPS[slot]
    # Core terms every run; expanded campus-language terms rotate every 10 minutes.
    browser_terms = CORE_TERMS + expansion
    # Search-engine matrix is intentionally smaller to avoid unnecessary rate limiting.
    engine_terms = CORE_TERMS + expansion[:3]
    counts = {}

    data = load_data()
    before = sum(1 for x in data["items"] if x.get("source") == "Threads")

    browser_candidates = collect_threads_browser(browser_terms)
    added_browser = add_verified(data, browser_candidates, counts, limit=100)
    print(f"[threads_deep] browser candidates={len(browser_candidates)} added={added_browser}")

    engine_candidates = collect_search_engines(engine_terms)
    added_engines = add_verified(data, engine_candidates, counts, limit=140)
    print(f"[threads_deep] engine candidates={len(engine_candidates)} added={added_engines}")

    data = load_data()
    total_threads = sum(1 for x in data["items"] if x.get("source") == "Threads")
    for health in data.get("source_health", []):
        if health.get("task") == "threads":
            health.setdefault("engine_counts", {}).update(counts)
            health["count"] = total_threads
            health["deep_search_last_run"] = NOW().isoformat()
            health["deep_search_terms"] = browser_terms
    checkpoint(data)
    print(
        f"[threads_deep] completed slot={slot} terms={len(browser_terms)} "
        f"before={before} added={added_browser + added_engines} total_threads={total_threads} counts={counts}"
    )


if __name__ == "__main__":
    main()
