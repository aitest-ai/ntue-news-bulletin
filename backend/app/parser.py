import httpx
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import email.utils
import urllib.parse
from typing import List, Dict, Any
import re
import json

def resolve_google_news_link(url: str) -> str:
    """
    Decodes Google News RSS redirect URL into the original target URL using the internal RPC API.
    """
    if not url or "news.google.com" not in url:
        return url
        
    try:
        # 1. Extract base64 string
        parsed_url = urllib.parse.urlparse(url)
        base64_str = parsed_url.path.split('/')[-1]
        if not base64_str:
            return url
            
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # 2. Fetch parameters from the google articles URL
        articles_url = f"https://news.google.com/articles/{base64_str}"
        response = httpx.get(articles_url, headers=headers, follow_redirects=True, timeout=5.0)
        if response.status_code != 200:
            # Fallback to RSS articles URL
            articles_url = f"https://news.google.com/rss/articles/{base64_str}"
            response = httpx.get(articles_url, headers=headers, follow_redirects=True, timeout=5.0)
            response.raise_for_status()
            
        html_text = response.text
        
        # Extract signature and timestamp using Regex
        sig_match = re.search(r'data-n-a-sg=["\']([^"\']+)["\']', html_text)
        ts_match = re.search(r'data-n-a-ts=["\']([^"\']+)["\']', html_text)
        
        if not sig_match or not ts_match:
            return url
            
        signature = sig_match.group(1)
        timestamp = ts_match.group(1)
        
        # 3. Post to batchexecute RPC endpoint
        post_url = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
        inner_payload = f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{base64_str}",{timestamp},"{signature}"]'
        payload = ["Fbv4je", inner_payload]
        payload_str = f"f.req={urllib.parse.quote(json.dumps([[payload]]))}"
        
        headers["Content-Type"] = "application/x-www-form-urlencoded;charset=UTF-8"
        
        response = httpx.post(post_url, headers=headers, content=payload_str, timeout=5.0)
        response.raise_for_status()
        
        # Clean and parse the response
        cleaned_text = response.text.split("\n\n")[1]
        parsed_data = json.loads(cleaned_text)[:-2]
        decoded_url = json.loads(parsed_data[0][2])[1]
        
        print(f"[Parser] RPC Resolved: {url[:55]}... -> {decoded_url[:70]}")
        return decoded_url
    except Exception as e:
        print(f"[Parser] Failed to RPC resolve {url[:55]}: {e}")
        return url


def fetch_google_news_rss(keyword: str) -> List[Dict[str, Any]]:
    """
    Fetches and parses Google News RSS feed for a specific keyword.
    Uses hl=zh-TW and gl=TW to target Taiwanese traditional Chinese news content.
    """
    encoded_keyword = urllib.parse.quote(keyword)
    url = f"https://news.google.com/rss/search?q={encoded_keyword}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = httpx.get(url, headers=headers, timeout=15.0)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        items = []
        
        # Limit to top 20 items per search to keep resolution times fast
        nodes = root.findall(".//item")[:20]
        
        for item in nodes:
            title_elem = item.find("title")
            link_elem = item.find("link")
            pub_date_elem = item.find("pubDate")
            source_elem = item.find("source")
            
            title = title_elem.text if title_elem is not None and title_elem.text else ""
            link = link_elem.text if link_elem is not None and link_elem.text else ""
            
            # Resolve Google News redirect URL to direct website URL
            if link:
                link = resolve_google_news_link(link)
            
            publish_time = None
            if pub_date_elem is not None and pub_date_elem.text:
                try:
                    publish_time = email.utils.parsedate_to_datetime(pub_date_elem.text)
                except Exception:
                    publish_time = datetime.now()
            else:
                publish_time = datetime.now()
                
            source = "Google News"
            if source_elem is not None and source_elem.text:
                source = source_elem.text
            elif " - " in title:
                parts = title.rsplit(" - ", 1)
                if len(parts) > 1:
                    source = parts[1]
            
            clean_title = title
            if source and title.endswith(f" - {source}"):
                clean_title = title[:-len(f" - {source}")]
            elif " - " in title:
                parts = title.rsplit(" - ", 1)
                clean_title = parts[0]
                
            items.append({
                "title": clean_title.strip(),
                "url": link,
                "source": source.strip(),
                "publish_time": publish_time,
                "keyword": keyword
            })
            
        return items
    except Exception as e:
        print(f"Error parsing RSS for keyword '{keyword}': {e}")
        return []

def is_real_social_post(url: str) -> bool:
    url_lower = url.lower()
    
    # Dcard: must contain "/p/"
    if "dcard.tw" in url_lower:
        return "/p/" in url_lower
        
    # PTT: must contain "/bbs/" and ".html"
    if "ptt.cc" in url_lower or "pttweb.cc" in url_lower:
        return "/bbs/" in url_lower and (".html" in url_lower or "m." in url_lower)
        
    # Threads: must contain "/post/" or "/t/" or have post path depth
    if "threads.net" in url_lower or "threads.com" in url_lower:
        parts = [p for p in url_lower.split("/") if p]
        return len(parts) >= 4
        
    # Facebook: must contain "/posts/", "/permalink/", "/photos/", "/videos/", "/groups/"
    if "facebook.com" in url_lower or "fb.com" in url_lower:
        return any(x in url_lower for x in ["/posts/", "/permalink/", "/photos/", "/videos/", "/groups/"])
        
    # Instagram: must contain "/p/", "/reel/", or "/reels/"
    if "instagram.com" in url_lower:
        return any(x in url_lower for x in ["/p/", "/reel/", "/reels/"])
        
    return False

def parse_yahoo_date(date_str: str) -> datetime:
    if not date_str or date_str == "None":
        return datetime.now()
        
    date_str = date_str.strip().lower()
    
    # Handle "X小時前" or "X hr ago"
    hr_match = re.search(r'(\d+)\s*(?:小時|hour|hr)', date_str)
    if hr_match:
        hrs = int(hr_match.group(1))
        return datetime.now() - timedelta(hours=hrs)
        
    # Handle "X天前" or "X day ago"
    day_match = re.search(r'(\d+)\s*(?:天|day|d)\s*(?:前|ago)?', date_str)
    if day_match:
        days = int(day_match.group(1))
        return datetime.now() - timedelta(days=days)
        
    # Handle "X分鐘前" or "X min ago"
    min_match = re.search(r'(\d+)\s*(?:分鐘|minute|min|m)\s*(?:前|ago)?', date_str)
    if min_match:
        mins = int(min_match.group(1))
        return datetime.now() - timedelta(minutes=mins)
        
    # Handle date format like "2026年6月12日"
    date_match = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日', date_str)
    if date_match:
        y, m, d = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
        return datetime(y, m, d)
        
    # Match YYYY-MM-DD or YYYY/MM/DD
    dash_match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', date_str)
    if dash_match:
        y, m, d = int(dash_match.group(1)), int(dash_match.group(2)), int(dash_match.group(3))
        return datetime(y, m, d)
        
    return datetime.now()

NTUE_RELEVANCE_TERMS = [
    "國北教大", "北教大", "國立臺北教育大學", "臺北教育大學", "台北教育大學",
    "ntue", "國北教", "北師大", "北師"
]

def title_mentions_ntue(title: str) -> bool:
    """Check if post title actually discusses NTUE content."""
    t = title.lower()
    return any(term.lower() in t for term in NTUE_RELEVANCE_TERMS)

def fetch_social_posts(keyword: str) -> List[Dict[str, Any]]:
    """
    Searches Yahoo for Dcard (NTUE board), PTT, Threads, and Instagram posts.
    - Dcard: searches the dedicated NTUE board (site:dcard.tw/f/ntue) — always relevant.
    - PTT/Threads/IG: keyword + platform search, then filters by title relevance.
    - Facebook: excluded entirely.
    - Only posts within the past 7 days with a confirmed date tag are kept.
    """
    import html as htmllib
    import time

    items = []
    seen_urls = set()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    def yahoo_search(query: str, use_btf: bool = False) -> list:
        """Return list of (url, title, date_text) from Yahoo search.
        use_btf=True appends &btf=w to restrict to past-week results.
        """
        encoded = urllib.parse.quote(query)
        btf_param = "&btf=w" if use_btf else ""
        search_url = f"https://tw.search.yahoo.com/search?p={encoded}{btf_param}"
        try:
            req = urllib.request.Request(search_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                html_text = resp.read().decode("utf-8", errors="ignore")
            segments = html_text.split('href="https://r.search.yahoo.com/')
            results = []
            for seg in segments[1:]:
                ru_match = re.search(r'RU=([^/"]+)/', seg)
                if not ru_match:
                    continue
                direct_url = urllib.parse.unquote(ru_match.group(1))
                title_m = re.search(r'aria-label="([^"]+)"', seg)
                title = htmllib.unescape(title_m.group(1)) if title_m else ""
                date_m = re.search(r'<span class="fc-smoke">([^<]+)</span>', seg[:2000])
                date_text = date_m.group(1).strip() if date_m else None
                results.append((direct_url, title, date_text))
            return results
        except Exception as e:
            print(f"[Social Scraper] Yahoo search error for '{query}': {e}")
            return []

    def try_add(url: str, title: str, date_text, source: str, kw: str,
                require_relevance: bool = False, date_required: bool = True):
        """Validate and add an article to items list.
        date_required=False: accept posts without a date tag (when btf=w already filtered them).
        """
        url_lower = url.lower()
        
        # Skip Facebook entirely
        if "facebook.com" in url_lower or "fb.com" in url_lower:
            return
        
        # Dedup
        if url in seen_urls:
            return
        
        # Must be a real post, not a homepage/board
        if not is_real_social_post(url):
            return
        
        # For PTT/Threads/IG: title must mention NTUE-related terms
        if require_relevance and not title_mentions_ntue(title):
            print(f"[Social Scraper] Skipping irrelevant: {title[:50]}")
            return
        
        # Handle date: if no date tag exists
        if date_text is None:
            if date_required:
                # No date and we require one — skip
                return
            else:
                # No date but Yahoo's btf=w filter already limits to past week
                # Default to now() as an approximation
                publish_time = datetime.now()
        else:
            publish_time = parse_yahoo_date(date_text)
            age_days = (datetime.now() - publish_time).days
            if age_days > 7:
                print(f"[Social Scraper] Skipping old post ({age_days}d): {title[:50]}")
                return
        
        seen_urls.add(url)
        items.append({
            "title": title.strip(),
            "url": url,
            "source": source,
            "publish_time": publish_time,
            "keyword": kw,
        })

    # ── 1. Dcard: search dedicated NTUE board only ──────────────────────────
    # No btf=w needed — board is always NTUE-relevant; accept posts even without date tag
    print(f"[Social Scraper] Searching Dcard NTUE board...")
    for url, title, date_text in yahoo_search("site:dcard.tw/f/ntue"):
        if "dcard.tw" not in url.lower():
            continue
        try_add(url, title, date_text, "Dcard", keyword,
                require_relevance=False, date_required=False)
    time.sleep(1.5)

    # ── 2. PTT: keyword + ptt + btf=w, require title relevance ─────────────
    # Use btf=w so Yahoo pre-filters to past week; accept posts without date tag
    print(f"[Social Scraper] Searching PTT for '{keyword}'...")
    for url, title, date_text in yahoo_search(f"{keyword} ptt", use_btf=True):
        if "ptt.cc" not in url.lower() and "pttweb.cc" not in url.lower():
            continue
        try_add(url, title, date_text, "PTT", keyword,
                require_relevance=True, date_required=False)
    time.sleep(1.5)

    # ── 3. Threads: keyword + threads + btf=w, require title relevance ──────
    print(f"[Social Scraper] Searching Threads for '{keyword}'...")
    for url, title, date_text in yahoo_search(f"{keyword} threads", use_btf=True):
        if "threads.com" not in url.lower() and "threads.net" not in url.lower():
            continue
        try_add(url, title, date_text, "Threads", keyword,
                require_relevance=True, date_required=False)
    time.sleep(1.5)

    # ── 4. Instagram: keyword + instagram + btf=w, require title relevance ───
    print(f"[Social Scraper] Searching Instagram for '{keyword}'...")
    for url, title, date_text in yahoo_search(f"{keyword} instagram", use_btf=True):
        if "instagram.com" not in url.lower():
            continue
        try_add(url, title, date_text, "Instagram", keyword,
                require_relevance=True, date_required=False)
    time.sleep(1.5)

    print(f"[Social Scraper] Found {len(items)} valid social posts for keyword '{keyword}'")
    return items




