#!/usr/bin/env python3
import email.utils
import html
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs

TAIPEI = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "frontend" / "public" / "data"
OUT_FILE = OUT_DIR / "news.json"

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


def request_text(url, headers=None, timeout=18):
    base_headers = {
        "User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/150 Safari/537.36",
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
        if not title or not link:
            continue
        rows.append({"title":title,"url":link,"publisher":urlparse(link).netloc or "Bing Web","publish_time":None,"description":desc,"discovery":"bing_web"})
    return rows


def fetch_duckduckgo_html(query, limit=40):
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q":query})
    page = request_text(url, headers={"Referer":"https://duckduckgo.com/"}, timeout=20)
    rows = []
    blocks = re.findall(r'<div class="result[^>]*>(.*?)</div>\s*</div>', page, re.I | re.S)
    if not blocks:
        blocks = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, re.I | re.S)
        for href, title_html in blocks[:limit]:
            link = html.unescape(href)
            if "uddg=" in link:
                qs = parse_qs(urlparse(link).query)
                link = qs.get("uddg", [link])[0]
            title = re.sub(r"<[^>]+>", "", html.unescape(title_html)).strip()
            rows.append({"title":title,"url":link,"publisher":urlparse(link).netloc or "DuckDuckGo","publish_time":None,"description":"","discovery":"duckduckgo"})
        return rows

    for block in blocks[:limit]:
        m = re.search(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.I | re.S)
        if not m:
            continue
        link = html.unescape(m.group(1))
        if "uddg=" in link:
            qs = parse_qs(urlparse(link).query)
            link = qs.get("uddg", [link])[0]
        title = re.sub(r"<[^>]+>", "", html.unescape(m.group(2))).strip()
        sm = re.search(r'class="result__snippet"[^>]*>(.*?)</', block, re.I | re.S)
        desc = re.sub(r"<[^>]+>", "", html.unescape(sm.group(1))).strip() if sm else ""
        rows.append({"title":title,"url":link,"publisher":urlparse(link).netloc or "DuckDuckGo","publish_time":None,"description":desc,"discovery":"duckduckgo"})
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


def normalize_threads_url(link):
    link = html.unescape(link or "").replace("\\/", "/")
    if link.startswith("//"):
        link = "https:" + link
    parsed = urlparse(link)
    host = (parsed.netloc or "").lower()
    if host not in {"threads.com","www.threads.com","threads.net","www.threads.net"}:
        return ""
    if "/post/" not in parsed.path or "/@" not in parsed.path:
        return ""
    return f"https://www.threads.com{parsed.path}".split("?",1)[0]


def extract_threads_candidate(row):
    link = normalize_threads_url(row.get("url"))
    if not link:
        return None
    searchable = f'{row.get("title", "")} {row.get("description", "")}'
    matched = relevance_keyword(searchable)
    if not matched:
        return None
    return {
        "title": row.get("title") or searchable[:300],
        "url": link,
        "source": "Threads",
        "publisher": row.get("publisher") or "Threads",
        "publish_time": row.get("publish_time"),
        "discovered_at": now_local().isoformat(),
        "keyword": matched,
        "task": "threads",
        "discovery": row.get("discovery") or "public_search",
    }


def fetch_threads_direct_search():
    headers = {"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/150 Safari/537.36"}
    found = []
    for keyword in KEYWORDS:
        for base in ("https://www.threads.com/search/", "https://www.threads.net/search"):
            url = base + "?" + urllib.parse.urlencode({"q":keyword,"serp_type":"recent"})
            try:
                page = request_text(url, headers=headers, timeout=18)
            except Exception as exc:
                print(f"[threads:direct:{keyword}] failed: {exc}", file=sys.stderr)
                continue
            normalized = page.replace("\\/", "/").replace("\\u0026", "&")
            for candidate in re.findall(r'https?://(?:www\.)?threads\.(?:com|net)/@[^"\'<>\\\s]+/post/[A-Za-z0-9_-]+', normalized, re.I):
                link = normalize_threads_url(candidate)
                if link:
                    found.append({"title":keyword,"url":link,"publisher":"Threads","publish_time":None,"description":keyword,"discovery":"threads_direct"})
            for path in re.findall(r'(/@[^"\'<>\\\s]+/post/[A-Za-z0-9_-]+)', normalized, re.I):
                found.append({"title":keyword,"url":"https://www.threads.com"+path,"publisher":"Threads","publish_time":None,"description":keyword,"discovery":"threads_direct"})
    return found


def enrich_threads_public_page(item):
    try:
        page = request_text(item["url"], timeout=14)
    except Exception:
        return item
    text = meta_content(page, "og:description") or meta_content(page, "og:title")
    if text:
        matched = relevance_keyword(text)
        if not matched:
            return None
        item["title"] = text[:300]
        item["keyword"] = matched
    author_match = re.search(r'/@([^/]+)/post/', item["url"])
    if author_match:
        item["publisher"] = author_match.group(1)
    taken = re.search(r'"taken_at"\s*:\s*(\d{10})', page)
    if taken:
        try:
            item["publish_time"] = datetime.fromtimestamp(int(taken.group(1)), timezone.utc).astimezone(TAIPEI).isoformat()
        except Exception:
            pass
    return item


def fetch_threads_task():
    rows = []
    counts = {"threads_direct":0,"google_news":0,"bing_web":0,"duckduckgo":0}
    queries = []
    for keyword in KEYWORDS:
        queries.extend([
            ("google_news", f'"{keyword}" (site:threads.com OR site:threads.net) when:90d'),
            ("bing_web", f'"{keyword}" (site:threads.com OR site:threads.net)'),
            ("duckduckgo", f'"{keyword}" site:threads.com/@'),
            ("duckduckgo", f'"{keyword}" site:threads.net/@'),
        ])

    rows.extend(fetch_threads_direct_search())
    counts["threads_direct"] = len(rows)

    for engine, query in queries:
        try:
            if engine == "google_news":
                batch = fetch_google_news_rss(query, 90, 100)
            elif engine == "bing_web":
                batch = fetch_bing_web_rss(query, 50)
            else:
                batch = fetch_duckduckgo_html(query, 40)
        except Exception as exc:
            print(f"[threads:{engine}] failed: {exc}", file=sys.stderr)
            continue
        for row in batch:
            candidate = extract_threads_candidate(row)
            if candidate:
                rows.append(candidate)
                counts[engine] += 1

    provisional = []
    for row in rows:
        if row.get("source") != "Threads":
            candidate = extract_threads_candidate(row)
            if candidate:
                provisional.append(candidate)
        else:
            provisional.append(row)

    provisional = deduplicate(provisional)
    enriched = []
    for item in provisional[:100]:
        checked = enrich_threads_public_page(item.copy())
        if checked:
            enriched.append(checked)
    return deduplicate(enriched + provisional), counts


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
        threads_items, thread_counts = fetch_threads_task()
        fresh.extend(threads_items)
        health.append({"task":"threads","source":"Threads","status":"healthy","count":len(threads_items),"error":None,"engine_counts":thread_counts})
        print(f"[threads] {len(threads_items)} items {thread_counts}")
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
    kept = kept[:1500]
    pubs = sorted({x.get("publisher") or x.get("source") for x in kept if x.get("task") == "google_news"})
    payload = {
        "schema_version":8,
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
