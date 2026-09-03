#!/usr/bin/env python3
import email.utils
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

TAIPEI = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "frontend" / "public" / "data"
OUT_FILE = OUT_DIR / "news.json"
THREADS_STATE_FILE = OUT_DIR / "threads-state.json"
THREADS_OFFICIAL_REFRESH_HOURS = 3

KEYWORDS = [
    "國立臺北教育大學",
    "國北教大",
    "北教大",
    "NTUE",
    "National Taipei University of Education",
]

RELEVANCE_TERMS = [
    "國立臺北教育大學", "國立台北教育大學", "臺北教育大學", "台北教育大學",
    "國北教大", "國北教", "北教大", "國北", "NTUE",
    "National Taipei University of Education",
]

SOCIAL_TASKS = [
    {"task":"dcard","source":"Dcard","google_filter":"site:dcard.tw/f/ntue","bing_filter":"site:dcard.tw/f/ntue","domains":("dcard.tw",),"days":45},
    {"task":"ptt","source":"PTT","google_filter":"site:ptt.cc","bing_filter":"site:ptt.cc/bbs","domains":("ptt.cc",),"days":60},
    {"task":"instagram","source":"Instagram","google_filter":"site:instagram.com","bing_filter":"site:instagram.com","domains":("instagram.com",),"days":45},
]


def now_local():
    return datetime.now(TAIPEI)


def normalize_text(value):
    return " ".join((value or "").replace("臺", "台").lower().split())


def relevance_keyword(text):
    norm = normalize_text(text)
    for term in RELEVANCE_TERMS:
        if normalize_text(term) in norm:
            for keyword in KEYWORDS:
                if normalize_text(keyword) in norm:
                    return keyword
            if "ntue" in norm:
                return "NTUE"
            if "北教" in norm or "國北" in norm:
                return "國北教大"
            return "國立臺北教育大學"
    return None


def parse_rfc822(value):
    if not value:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(TAIPEI)
        return dt if dt.year > 1971 else None
    except Exception:
        return None


def parse_iso(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(TAIPEI)
        return dt if dt.year > 1971 else None
    except Exception:
        return None


def request_text(url, headers=None, timeout=18):
    base_headers = {
        "User-Agent":"Mozilla/5.0 NTUE-Opinion-Monitor/6.0",
        "Accept-Language":"zh-TW,zh;q=0.9,en;q=0.7",
    }
    if headers:
        base_headers.update(headers)
    req = urllib.request.Request(url, headers=base_headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def fetch_google_news_rss(query, max_days, limit=100):
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    root = ET.fromstring(request_text(url))
    cutoff = now_local() - timedelta(days=max_days)
    rows = []
    for node in root.findall(".//item")[:limit]:
        raw = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        pub = (node.findtext("pubDate") or "").strip()
        if not raw or not link:
            continue
        dt = parse_rfc822(pub)
        if not dt or dt < cutoff:
            continue
        sn = node.find("source")
        publisher = sn.text.strip() if sn is not None and sn.text else "Google News"
        title = raw.rsplit(" - ", 1)[0].strip() if " - " in raw else raw
        rows.append({"title":title,"url":link,"publisher":publisher,"publish_time":dt.isoformat(),"description":"","discovery":"google_news"})
    return rows


def fetch_bing_web_rss(query, limit=50):
    encoded = urllib.parse.quote(query)
    url = f"https://www.bing.com/search?q={encoded}&format=rss&setlang=zh-Hant&mkt=zh-TW"
    root = ET.fromstring(request_text(url))
    rows = []
    for node in root.findall(".//item")[:limit]:
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        desc = (node.findtext("description") or "").strip()
        pub = (node.findtext("pubDate") or "").strip()
        if not title or not link:
            continue
        dt = parse_rfc822(pub)
        rows.append({"title":title,"url":link,"publisher":urlparse(link).netloc or "Bing Web","publish_time":dt.isoformat() if dt else None,"description":desc,"discovery":"bing_web"})
    return rows


def fetch_news_task():
    items, seen, counts = [], set(), {}
    for keyword in KEYWORDS:
        rows = fetch_google_news_rss(f'"{keyword}" when:30d', 30, 100)
        counts[keyword] = len(rows)
        for row in rows:
            if row["url"] in seen:
                continue
            seen.add(row["url"])
            items.append({"title":row["title"],"url":row["url"],"source":row["publisher"],"publisher":row["publisher"],"publish_time":row["publish_time"],"discovered_at":now_local().isoformat(),"keyword":keyword,"task":"google_news","discovery":"google_news"})
    return items, counts


def domain_allowed(url, domains):
    host = (urlparse(url).netloc or "").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def fetch_social_task(spec):
    items, seen_urls, seen_titles = [], set(), set()
    engine_counts = {"google_news":0,"bing_web":0}
    for keyword in KEYWORDS:
        queries = [
            ("google_news", f'"{keyword}" {spec["google_filter"]} when:{spec["days"]}d'),
            ("bing_web", f'"{keyword}" {spec["bing_filter"]}'),
        ]
        for engine, query in queries:
            try:
                rows = fetch_google_news_rss(query, spec["days"], 100) if engine == "google_news" else fetch_bing_web_rss(query, 50)
            except Exception as exc:
                print(f'[{spec["task"]}:{engine}:{keyword}] failed: {exc}', file=sys.stderr)
                continue
            for row in rows:
                if engine == "bing_web" and not domain_allowed(row["url"], spec["domains"]):
                    continue
                matched = relevance_keyword(f'{row["title"]} {row.get("description", "")}')
                if not matched:
                    continue
                uk = row["url"].split("#", 1)[0]
                tk = (normalize_text(row["title"]), spec["source"])
                if uk in seen_urls or tk in seen_titles:
                    continue
                seen_urls.add(uk); seen_titles.add(tk); engine_counts[engine] += 1
                items.append({"title":row["title"],"url":row["url"],"source":spec["source"],"publisher":row["publisher"],"publish_time":row["publish_time"],"discovered_at":now_local().isoformat(),"keyword":matched,"task":spec["task"],"discovery":engine})
    return items, engine_counts


def load_threads_state():
    if not THREADS_STATE_FILE.exists():
        return {"last_official_fetch":None,"items":[]}
    try:
        data = json.loads(THREADS_STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"last_official_fetch":None,"items":[]}
    except Exception:
        return {"last_official_fetch":None,"items":[]}


def save_threads_state(items):
    THREADS_STATE_FILE.write_text(json.dumps({
        "last_official_fetch": now_local().isoformat(),
        "items": items[:500],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def threads_cache_is_fresh(state):
    dt = parse_iso(state.get("last_official_fetch"))
    return bool(dt and now_local() - dt < timedelta(hours=THREADS_OFFICIAL_REFRESH_HOURS))


def fetch_threads_official_api(token):
    rows, seen = [], set()
    since = (now_local() - timedelta(days=30)).isoformat()
    until = now_local().isoformat()
    fields = "id,text,timestamp,permalink,username"
    for keyword in KEYWORDS:
        params = urllib.parse.urlencode({
            "q": keyword,
            "search_type": "RECENT",
            "search_mode": "KEYWORD",
            "fields": fields,
            "limit": 50,
            "since": since,
            "until": until,
            "access_token": token,
        })
        next_url = f"https://graph.threads.net/keyword_search?{params}"
        pages = 0
        while next_url and pages < 2:
            pages += 1
            try:
                data = json.loads(request_text(next_url, timeout=25))
            except Exception as exc:
                print(f"[threads:official:{keyword}:page{pages}] failed: {exc}", file=sys.stderr)
                break
            if isinstance(data, dict) and data.get("error"):
                print(f"[threads:official:{keyword}] API error: {data['error']}", file=sys.stderr)
                break
            for post in data.get("data", []):
                text = (post.get("text") or "").strip()
                matched = relevance_keyword(text)
                permalink = post.get("permalink") or ""
                pid = str(post.get("id") or permalink)
                if not text or not matched or not pid or pid in seen:
                    continue
                seen.add(pid)
                dt = parse_iso(post.get("timestamp"))
                rows.append({"title":text[:300],"url":permalink,"source":"Threads","publisher":post.get("username") or "Threads","publish_time":dt.isoformat() if dt else None,"discovered_at":now_local().isoformat(),"keyword":matched,"task":"threads","discovery":"threads_official"})
            next_url = ((data.get("paging") or {}).get("next") or "").strip()
    return rows


def fetch_threads_official():
    token = (os.getenv("THREADS_ACCESS_TOKEN") or "").strip()
    if not token:
        return [], {"status":"token_missing","fresh":0,"cached":0}

    state = load_threads_state()
    cached = [x for x in state.get("items", []) if isinstance(x, dict)]
    if threads_cache_is_fresh(state):
        return cached, {"status":"cached","fresh":0,"cached":len(cached)}

    fresh = fetch_threads_official_api(token)
    merged = deduplicate(fresh + cached)
    cutoff = now_local() - timedelta(days=60)
    kept = [x for x in merged if (retention_datetime(x) and retention_datetime(x) >= cutoff)]
    save_threads_state(kept)
    return kept, {"status":"refreshed","fresh":len(fresh),"cached":len(kept)}


def meta_content(page, prop):
    patterns = [
        rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(prop)}["\']',
    ]
    for pattern in patterns:
        m = re.search(pattern, page, re.I | re.S)
        if m:
            return html.unescape(m.group(1)).strip()
    return ""


def fetch_threads_anonymous():
    headers = {"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/150 Safari/537.36"}
    links, seen_links = [], set()
    for keyword in KEYWORDS:
        urls = [
            "https://www.threads.com/search/?" + urllib.parse.urlencode({"q":keyword,"serp_type":"recent"}),
            "https://www.threads.net/search?q=" + urllib.parse.quote(keyword),
        ]
        for url in urls:
            try:
                page = request_text(url, headers=headers, timeout=18)
            except Exception as exc:
                print(f"[threads:web:{keyword}] failed: {exc}", file=sys.stderr)
                continue
            normalized = page.replace("\\/", "/").replace("\\u0026", "&")
            candidates = re.findall(r'https?://(?:www\.)?threads\.(?:com|net)/@[^"\'<>\\\s]+/post/[A-Za-z0-9_-]+', normalized, re.I)
            candidates += ['https://www.threads.com' + p for p in re.findall(r'(/@[^"\'<>\\\s]+/post/[A-Za-z0-9_-]+)', normalized, re.I)]
            for link in candidates:
                link = link.split("?", 1)[0]
                if link not in seen_links:
                    seen_links.add(link); links.append(link)
        if len(links) >= 60:
            break

    items = []
    for link in links[:60]:
        try:
            page = request_text(link, headers=headers, timeout=14)
        except Exception:
            continue
        text = meta_content(page, "og:description") or meta_content(page, "og:title")
        matched = relevance_keyword(text)
        if not text or not matched:
            continue
        taken = re.search(r'"taken_at"\s*:\s*(\d{10})', page)
        dt = datetime.fromtimestamp(int(taken.group(1)), timezone.utc).astimezone(TAIPEI) if taken else None
        author_match = re.search(r'/@([^/]+)/post/', link)
        author = author_match.group(1) if author_match else "Threads"
        items.append({"title":text[:300],"url":link,"source":"Threads","publisher":author,"publish_time":dt.isoformat() if dt else None,"discovered_at":now_local().isoformat(),"keyword":matched,"task":"threads","discovery":"threads_web"})
    return deduplicate(items), len(items)


def fetch_threads_search_fallback():
    spec = {"task":"threads","source":"Threads","google_filter":"site:threads.com OR site:threads.net","bing_filter":"site:threads.com OR site:threads.net","domains":("threads.com","threads.net"),"days":60}
    return fetch_social_task(spec)


def fetch_threads_task():
    combined = []
    counts = {"official":0,"official_status":"token_missing","threads_web":0,"google_news":0,"bing_web":0}
    official, official_meta = fetch_threads_official()
    counts["official"] = len(official)
    counts["official_status"] = official_meta.get("status", "unknown")
    counts["official_fresh"] = official_meta.get("fresh", 0)

    web_items, web_count = fetch_threads_anonymous()
    counts["threads_web"] = web_count

    fallback, engines = fetch_threads_search_fallback()
    counts["google_news"] = engines.get("google_news", 0)
    counts["bing_web"] = engines.get("bing_web", 0)

    combined = deduplicate(official + web_items + fallback)
    return combined, counts


def load_previous():
    if not OUT_FILE.exists():
        return []
    try:
        data = json.loads(OUT_FILE.read_text(encoding="utf-8"))
        return data.get("items", []) if isinstance(data, dict) else []
    except Exception:
        return []


def deduplicate(items):
    seen_urls, seen_titles, result = set(), set(), []
    for item in items:
        uk = (item.get("url") or "").split("#", 1)[0]
        tk = (normalize_text(item.get("title")), normalize_text(item.get("source")))
        if (uk and uk in seen_urls) or tk in seen_titles:
            continue
        if uk:
            seen_urls.add(uk)
        seen_titles.add(tk)
        result.append(item)
    return result


def previous_item_is_valid(item):
    if item.get("task") == "google_news":
        return True
    return bool(relevance_keyword(f'{item.get("title", "")} {item.get("description", "")}'))


def retention_datetime(item):
    for key in ("publish_time", "discovered_at"):
        value = item.get(key)
        if not value:
            continue
        try:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TAIPEI)
            if dt.year > 1971:
                return dt
        except Exception:
            pass
    return None


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    health, fresh = [], []

    try:
        news_items, counts = fetch_news_task()
        fresh.extend(news_items)
        health.append({"task":"google_news","source":"新聞媒體","status":"healthy","count":len(news_items),"error":None,"keyword_counts":counts})
        print(f"[google_news] {len(news_items)} unique items")
    except Exception as exc:
        health.append({"task":"google_news","source":"新聞媒體","status":"failed","count":0,"error":str(exc)[:240]})
        print(f"[google_news] FAILED: {exc}", file=sys.stderr)

    for spec in SOCIAL_TASKS:
        try:
            task_items, engines = fetch_social_task(spec)
            fresh.extend(task_items)
            health.append({"task":spec["task"],"source":spec["source"],"status":"healthy","count":len(task_items),"error":None,"engine_counts":engines})
            print(f'[{spec["task"]}] {len(task_items)} items')
        except Exception as exc:
            health.append({"task":spec["task"],"source":spec["source"],"status":"failed","count":0,"error":str(exc)[:240]})
            print(f'[{spec["task"]}] FAILED: {exc}', file=sys.stderr)

    try:
        threads_items, threads_counts = fetch_threads_task()
        fresh.extend(threads_items)
        health.append({"task":"threads","source":"Threads","status":"healthy","count":len(threads_items),"error":None,"engine_counts":threads_counts})
        print(f"[threads] {len(threads_items)} items {threads_counts}")
    except Exception as exc:
        health.append({"task":"threads","source":"Threads","status":"failed","count":0,"error":str(exc)[:240]})
        print(f"[threads] FAILED: {exc}", file=sys.stderr)

    previous = [x for x in load_previous() if previous_item_is_valid(x)]
    combined = deduplicate(fresh + previous)
    cutoff = now_local() - timedelta(days=90)
    kept = []
    for item in combined:
        dt = retention_datetime(item)
        if dt and dt >= cutoff:
            kept.append(item)

    kept.sort(key=lambda x:x.get("publish_time") or x.get("discovered_at") or "", reverse=True)
    kept = kept[:1200]
    pubs = sorted({x.get("publisher") or x.get("source") for x in kept if x.get("task") == "google_news"})
    payload = {
        "schema_version":7,
        "updated_at":now_local().isoformat(),
        "keywords":KEYWORDS,
        "items":kept,
        "source_health":health,
        "summary":{
            "total":len(kept),
            "fresh_this_run":len(fresh),
            "healthy_tasks":sum(1 for h in health if h["status"] == "healthy"),
            "failed_tasks":sum(1 for h in health if h["status"] == "failed"),
            "news_publishers":len(pubs),
        },
    }
    OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(kept)} items, {len(pubs)} news publishers -> {OUT_FILE}")


if __name__ == "__main__":
    main()
