#!/usr/bin/env python3
import email.utils
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs

TAIPEI = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
NEWS_FILE = ROOT / "frontend" / "public" / "data" / "news.json"

TERMS = [
    "國立臺北教育大學", "國北教大", "北教大", "NTUE",
    "台北教育大學", "臺北教育大學", "#國北教大", "#北教大", "#NTUE",
]
RELEVANCE = [
    "國立臺北教育大學", "國立台北教育大學", "臺北教育大學", "台北教育大學",
    "國北教大", "國北教", "北教大", "國北", "NTUE",
]


def norm(s):
    return " ".join((s or "").replace("臺", "台").lower().split())


def relevant(text):
    n = norm(text)
    for term in RELEVANCE:
        if norm(term) in n:
            if "ntue" in n: return "NTUE"
            if "北教" in n or "國北" in n: return "國北教大"
            return "國立臺北教育大學"
    return None


def request_text(url, timeout=12):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 NTUE-Opinion-Monitor/8.0",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def is_threads_post(url):
    try:
        host = (urlparse(url).netloc or "").lower()
        path = urlparse(url).path
        return (host.endswith("threads.com") or host.endswith("threads.net")) and "/@" in path and "/post/" in path
    except Exception:
        return False


def canonical(url):
    if not url: return ""
    url = html.unescape(url).replace("threads.net", "threads.com")
    if url.startswith("//"): url = "https:" + url
    return url.split("?", 1)[0].split("#", 1)[0]


def parse_rfc822(v):
    if not v: return None
    try:
        dt = email.utils.parsedate_to_datetime(v)
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TAIPEI).isoformat()
    except Exception:
        return None


def google_news(query):
    url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(query) + "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    root = ET.fromstring(request_text(url))
    rows = []
    for n in root.findall(".//item")[:80]:
        title = (n.findtext("title") or "").strip()
        link = canonical((n.findtext("link") or "").strip())
        if not title or not link: continue
        rows.append((title, link, "", parse_rfc822(n.findtext("pubDate") or ""), "google_news"))
    return rows


def bing(query):
    url = "https://www.bing.com/search?q=" + urllib.parse.quote(query) + "&format=rss&setlang=zh-Hant&mkt=zh-TW"
    root = ET.fromstring(request_text(url))
    rows=[]
    for n in root.findall(".//item")[:60]:
        rows.append(((n.findtext("title") or "").strip(), canonical((n.findtext("link") or "").strip()), (n.findtext("description") or "").strip(), parse_rfc822(n.findtext("pubDate") or ""), "bing"))
    return rows


def ddg(query):
    page = request_text("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query))
    rows=[]
    for m in re.finditer(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, re.I|re.S):
        href = html.unescape(m.group(1)); title = re.sub(r"<[^>]+>", " ", m.group(2))
        if "uddg=" in href:
            try: href = urllib.parse.unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
            except Exception: pass
        rows.append((html.unescape(title).strip(), canonical(href), "", None, "duckduckgo"))
    return rows[:60]


def yahoo(query):
    page = request_text("https://tw.search.yahoo.com/search?p=" + urllib.parse.quote(query))
    rows=[]
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, re.I|re.S):
        href = html.unescape(m.group(1))
        if "RU=" in href:
            ru = re.search(r'/RU=([^/]+)/', href)
            if ru:
                try: href = urllib.parse.unquote(ru.group(1))
                except Exception: pass
        href = canonical(href)
        if not is_threads_post(href): continue
        title = html.unescape(re.sub(r"<[^>]+>", " ", m.group(2))).strip()
        rows.append((title, href, "", None, "yahoo"))
    return rows[:60]


def mojeek(query):
    page = request_text("https://www.mojeek.com/search?q=" + urllib.parse.quote(query))
    rows=[]
    for m in re.finditer(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', page, re.I|re.S):
        href = canonical(html.unescape(m.group(1)))
        if not is_threads_post(href): continue
        title = html.unescape(re.sub(r"<[^>]+>", " ", m.group(2))).strip()
        rows.append((title, href, "", None, "mojeek"))
    return rows[:60]


def meta_from_post(url):
    try: page = request_text(url, timeout=9)
    except Exception: return "", None
    text=""
    for key in ("og:description", "twitter:description", "og:title"):
        for pat in [
            rf'<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(key)}["\']',
        ]:
            m=re.search(pat,page,re.I|re.S)
            if m:
                text=html.unescape(m.group(1)).strip(); break
        if text: break
    ts=None
    m=re.search(r'"taken_at"\s*:\s*(\d{10})',page)
    if m:
        try: ts=datetime.fromtimestamp(int(m.group(1)),timezone.utc).astimezone(TAIPEI).isoformat()
        except Exception: pass
    return text,ts


def main():
    if not NEWS_FILE.exists():
        print("[threads_public_search] news.json missing")
        return
    data=json.loads(NEWS_FILE.read_text(encoding="utf-8")); items=data.get("items",[])
    existing={canonical(x.get("url") or "") for x in items}

    # Rotate three query terms per 10-minute slot; full sweep in about 30 minutes.
    slot=(datetime.now(TAIPEI).minute//10)%3
    selected=TERMS[slot*3:slot*3+3]
    if not selected: selected=TERMS[:3]
    counts={"google_news":0,"bing":0,"duckduckgo":0,"yahoo":0,"mojeek":0}
    candidates={}

    for term in selected:
        queries=[f'site:threads.com/@ "{term}"', f'site:threads.net/@ "{term}"']
        for q in queries:
            for engine,fn in [("google_news",google_news),("bing",bing),("duckduckgo",ddg),("yahoo",yahoo),("mojeek",mojeek)]:
                try: rows=fn(q)
                except Exception as e:
                    print(f"[threads_public_search:{engine}] {e}")
                    continue
                for title,url,desc,pub,_ in rows:
                    url=canonical(url)
                    if not is_threads_post(url) or url in existing: continue
                    matched=relevant(f"{title} {desc}")
                    candidates.setdefault(url,{"title":title,"desc":desc,"publish_time":pub,"matched":matched,"engine":engine})

    added=0
    for url,info in list(candidates.items())[:80]:
        text=info["title"] or info["desc"]
        pub=info["publish_time"]
        matched=info["matched"]
        if not matched:
            meta,meta_pub=meta_from_post(url)
            if meta:
                text=meta
                matched=relevant(meta)
                pub=pub or meta_pub
        if not matched: continue
        author="Threads"
        m=re.search(r'/@([^/]+)/post/',url)
        if m: author=m.group(1)
        items.append({"title":text[:300],"url":url,"source":"Threads","publisher":author,"publish_time":pub,"discovered_at":datetime.now(TAIPEI).isoformat(),"keyword":matched,"task":"threads","discovery":info["engine"]})
        existing.add(url); counts[info["engine"]]+=1; added+=1

    items.sort(key=lambda x:x.get("publish_time") or x.get("discovered_at") or "",reverse=True)
    data["items"]=items[:1800]
    for h in data.get("source_health",[]):
        if h.get("task")=="threads":
            h.setdefault("engine_counts",{}).update(counts)
            h["count"]=sum(1 for x in data["items"] if x.get("source")=="Threads")
    data.setdefault("summary",{})["total"]=len(data["items"])
    NEWS_FILE.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"[threads_public_search] terms={selected} candidates={len(candidates)} added={added} counts={counts}")

if __name__=="__main__": main()
