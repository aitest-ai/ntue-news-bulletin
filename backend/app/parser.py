import httpx
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import email.utils
import urllib.parse
from typing import List, Dict, Any, Tuple, Optional
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

from typing import Optional
import pytz

def parse_iso_datetime(iso_str: str) -> Optional[datetime]:
    iso_str = iso_str.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo:
            dt = dt.astimezone(pytz.utc).replace(tzinfo=None)
        return dt
    except Exception:
        m = re.search(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})', iso_str)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                int(m.group(4)), int(m.group(5)), int(m.group(6)))
            except Exception:
                pass
    return None

def parse_dcard_html_time(html: str) -> Optional[datetime]:
    import json
    import re
    from datetime import datetime, timedelta

    m = re.search(r'property="article:published_time"\s+content="([^"]+)"', html) or \
        re.search(r'content="([^"]+)"\s+property="article:published_time"', html)
    if m:
        t = parse_iso_datetime(m.group(1))
        if t:
            return t

    json_ld_matches = re.findall(r'<script\s+type="application/ld\+json">([\s\S]*?)</script>', html)
    for ld in json_ld_matches:
        try:
            data = json.loads(ld.strip())
            if isinstance(data, dict):
                dp = data.get("datePublished") or data.get("dateCreated")
                if dp:
                    t = parse_iso_datetime(dp)
                    if t:
                        return t
        except Exception:
            pass

    m_created = re.search(r'"createdAt"\s*:\s*"([^"]+)"', html)
    if m_created:
        t = parse_iso_datetime(m_created.group(1))
        if t:
            return t
            
    m_pub = re.search(r'"publishedAt"\s*:\s*"([^"]+)"', html)
    if m_pub:
        t = parse_iso_datetime(m_pub.group(1))
        if t:
            return t

    hr_match = re.search(r'(\d+)\s*(?:小時前|小時|hour|hr)', html)
    if hr_match:
        return datetime.utcnow() - timedelta(hours=int(hr_match.group(1)))
        
    day_match = re.search(r'(\d+)\s*(?:天前|天|day|d)', html)
    if day_match:
        return datetime.utcnow() - timedelta(days=int(day_match.group(1)))
        
    min_match = re.search(r'(\d+)\s*(?:分鐘前|分鐘|min|m)', html)
    if min_match:
        return datetime.utcnow() - timedelta(minutes=int(min_match.group(1)))
        
    if "剛剛" in html or "just now" in html:
        return datetime.utcnow()

    return None

def fetch_dcard_metadata(url: str) -> dict:
    import urllib.request
    import json
    import re
    
    res = {
        "title": "",
        "url": url,
        "forumName": "Dcard - 臺北教育大學板",
        "excerpt": "",
        "publishedAt": None,
        "commentCount": 0,
        "likeCount": 0
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9",
        "Referer": "https://www.dcard.tw/"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        # Max 1 retry
        with urllib.request.urlopen(req, timeout=5.0) as r:
            html = r.read().decode("utf-8", errors="ignore")
            
        res["publishedAt"] = parse_dcard_html_time(html)
        
        title_match = re.search(r"<title>([^<]+)</title>", html)
        if title_match:
            res["title"] = title_match.group(1).replace(" - Dcard", "").strip()
            
        desc_match = re.search(r'name="name"\s+content="([^"]+)"', html) or \
                     re.search(r'name="description"\s+content="([^"]+)"', html) or \
                     re.search(r'content="([^"]+)"\s+name="description"', html)
        if desc_match:
            res["excerpt"] = desc_match.group(1).strip()
            
        comment_match = re.search(r'"commentCount"\s*:\s*(\d+)', html)
        if comment_match:
            res["commentCount"] = int(comment_match.group(1))
            
        like_match = re.search(r'"likeCount"\s*:\s*(\d+)', html)
        if like_match:
            res["likeCount"] = int(like_match.group(1))
            
    except Exception as e:
        print(f"[Dcard Collector] Error fetching metadata for {url}: {e}")
        
    return res

def fetch_ptt_published_time(url: str) -> Optional[datetime]:
    import urllib.request
    import re
    
    if "pttweb.cc" in url.lower():
        m = re.search(r'/bbs/([^/]+)/([^/]+)', url)
        if m:
            board = m.group(1)
            post_id = m.group(2)
            url = f"https://www.ptt.cc/bbs/{board}/{post_id}.html"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Cookie": "over18=1",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5.0) as r:
            html = r.read().decode("utf-8", errors="ignore")
            
        meta_values = re.findall(r'<span class="article-meta-value">([^<]+)</span>', html)
        if len(meta_values) >= 4:
            time_str = meta_values[3].strip()
            clean_time_str = re.sub(r'\s+', ' ', time_str)
            return datetime.strptime(clean_time_str, "%a %b %d %H:%M:%S %Y")
    except Exception as e:
        print(f"[PTT Parser] Error fetching post page {url}: {e}")
    return None

def fetch_threads_via_googlebot(keyword: str) -> List[Dict[str, Any]]:
    """
    Scrapes Threads search results using a Googlebot User-Agent.
    Threads serves SSR (server-side rendered) content to Googlebot, containing
    embedded JSON with real post text and timestamps.
    """
    import urllib.parse as up
    import json as _json
    from datetime import datetime
    
    results = []
    seen_urls: set = set()

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    }

    kw_variants = [keyword]
    if "臺" in keyword:
        kw_variants.append(keyword.replace("臺", "台"))
    elif "台" in keyword:
        kw_variants.append(keyword.replace("台", "臺"))

    EXCLUDE_KEYWORDS = ["北投", "北科", "台北醫大", "台北教育大學", "台科", "ntpu"]
    
    def find_posts(obj, out_list):
        if isinstance(obj, dict):
            if 'post' in obj and isinstance(obj['post'], dict):
                out_list.append(obj['post'])
            for k, v in obj.items():
                find_posts(v, out_list)
        elif isinstance(obj, list):
            for v in obj:
                find_posts(v, out_list)

    for kw_var in kw_variants:
        if len(results) >= 15:
            break
        encoded = up.quote(kw_var)
        search_url = f"https://www.threads.net/search/?q={encoded}"
        try:
            r = httpx.get(search_url, headers=headers, timeout=20.0, follow_redirects=True)
            if r.status_code != 200:
                continue
            html_raw = r.text
            
            scripts = re.findall(r'<script type="application/json"([^>]*)>(.*?)</script>', html_raw, re.DOTALL)
            extracted_posts = []
            
            for attrs, content in scripts:
                if not content: continue
                if 'thread_items' in content or 'post' in content:
                    try:
                        data = _json.loads(content)
                        find_posts(data, extracted_posts)
                    except Exception:
                        pass
                        
            for p in extracted_posts:
                code = p.get('code')
                if not code: continue
                post_url = f"https://www.threads.net/t/{code}"
                
                if post_url in seen_urls: continue
                seen_urls.add(post_url)
                
                caption = p.get('caption')
                text = caption.get('text', '') if caption else ''
                if not text: continue
                
                kw_norm = kw_var.replace("臺", "台").lower()
                text_norm = text.replace("臺", "台").lower()
                
                # STRICT KEYWORD FILTER
                if kw_norm not in text_norm:
                    continue
                    
                skip = False
                for ew in EXCLUDE_KEYWORDS:
                    if ew.lower() in text_norm and ew.lower() not in kw_norm:
                        skip = True
                        break
                if skip: continue
                
                title_text = text[:80].strip()
                if not title_text:
                    title_text = f"Threads 貼文 - {kw_var}"
                    
                taken_at = p.get('taken_at')
                pub_time = datetime.fromtimestamp(taken_at) if taken_at else datetime.now()
                likes = p.get('like_count', 0)
                
                results.append({
                    "title": title_text,
                    "url": post_url,
                    "source": "Threads",
                    "publish_time": pub_time,
                    "keyword": keyword,
                    "engagement_count": likes,
                    "excerpt": text[:150]
                })
        except Exception as e:
            print(f"[Threads Googlebot] Request/Parsing failed for {kw_var}: {e}")

    print(f"[Threads Googlebot] Total found: {len(results)} posts for '{keyword}'")
    return results


def fetch_threads_via_official_api(keyword: str) -> Tuple[Optional[List[Dict[str, Any]]], str, Optional[str]]:
    """
    Calls Meta's official Threads /keyword_search endpoint if access token is set.
    Returns: (list_of_posts, status_string, error_message)
    """
    from .config import settings
    token = settings.THREADS_ACCESS_TOKEN
    version = settings.THREADS_API_VERSION or "v1.0"
    
    if not token:
        print("[Threads Collector] Warning: THREADS_ACCESS_TOKEN is not configured.")
        return None, "no_token", "Access token is missing in configuration."
        
    url = f"https://graph.threads.net/{version}/keyword_search"
    params = {
        "q": keyword,
        "search_type": "RECENT",
        "fields": "id,text,permalink,timestamp,username,like_count,reply_count,repost_count",
        "access_token": token
    }
    
    try:
        response = httpx.get(url, params=params, timeout=10.0)
        if response.status_code != 200:
            try:
                err_data = response.json()
                error_msg = err_data.get("error", {}).get("message", "Unknown API error")
                code = err_data.get("error", {}).get("code")
            except Exception:
                error_msg = response.text
                code = None
            
            # Check for permission errors
            if code == 10 or "permission" in error_msg.lower() or "threads_keyword_search" in error_msg.lower():
                print(f"[Threads Collector] Permission missing error: {error_msg}")
                return None, "permission_missing", error_msg
                
            print(f"[Threads Collector] API returned error status {response.status_code}: {error_msg}")
            return None, "api_error", error_msg
            
        data = response.json()
        posts_data = data.get("data", [])
        
        results = []
        for post in posts_data:
            text = post.get("text", "")
            title = text[:40] if text else "Threads 貼文"
            excerpt = text[:120] if text else ""
            
            likes = post.get("like_count", 0) or 0
            replies = post.get("reply_count", 0) or 0
            reposts = post.get("repost_count", 0) or 0
            engagement = likes + replies + reposts
            
            publish_time = None
            timestamp_str = post.get("timestamp")
            if timestamp_str:
                publish_time = parse_iso_datetime(timestamp_str)
                
            results.append({
                "title": title.strip(),
                "url": post.get("permalink", f"https://www.threads.net/post/{post.get('id')}"),
                "source": "Threads",
                "publish_time": publish_time,
                "keyword": keyword,
                "excerpt": excerpt,
                "engagement_count": engagement
            })
            
        print(f"[Threads Collector] Official API returned {len(results)} posts.")
        return results, "success", None
        
    except Exception as e:
        error_msg = str(e)
        print(f"[Threads Collector] Exception during official API call: {error_msg}")
        return None, "api_error", error_msg

PLAYWRIGHT_AVAILABLE = True

def fetch_threads_via_fallback(keyword: str) -> Tuple[List[Dict[str, Any]], List[str], str, Optional[str]]:
    """
    Search engine fallback route for Threads using Playwright to query search pages.
    Returns: (list_of_posts, queries_run, source_used, error_reason)
    """
    global PLAYWRIGHT_AVAILABLE
    import urllib.parse
    import re
    
    if not PLAYWRIGHT_AVAILABLE:
        print("[Threads Playwright] Playwright previously failed to initialize. Skipping to avoid hanging.")
        return [], [], "playwright_crawler", "playwright_not_available"
    
    # Check if playwright is available first
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[Threads Playwright] Playwright is not installed. Skipping.")
        PLAYWRIGHT_AVAILABLE = False
        return [], [], "playwright_crawler", "playwright_not_installed"
    
    results = []
    seen_urls = set()
    error_reason = None
    queries = [
        f"https://www.threads.net/search?q={urllib.parse.quote(keyword)}&serp_type=tags",
        f"https://www.threads.net/search?q={urllib.parse.quote(keyword)}"
    ]
    
    source_used = "playwright_crawler"
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="zh-TW",
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()
            
            for q_url in queries:
                print(f"[Threads Playwright] Navigating to: {q_url}")
                try:
                    response = page.goto(q_url, wait_until="load", timeout=15000)
                    
                    status = response.status if response else 200
                    if status == 429:
                        print(f"[Threads Playwright] Error: 429 Blocked on {q_url}")
                        error_reason = "request_blocked"
                        continue
                        
                    current_url = page.url
                    if "/login" in current_url:
                        print(f"[Threads Playwright] Warning: Redirected to login page on {q_url}")
                        error_reason = "login_required"
                        continue
                        
                    content = page.content()
                    if "too many requests" in content.lower():
                        print(f"[Threads Playwright] Error: 429 text detected on {q_url}")
                        error_reason = "request_blocked"
                        continue
                        
                    # Precise card text matching: only pull posts that contain the keyword in innerText
                    try:
                        # Wait for article selectors to load
                        page.wait_for_selector("article", timeout=6000)
                        articles = page.query_selector_all("article")
                        print(f"[Threads Playwright] Found {len(articles)} article cards. Filtering strictly by keyword '{keyword}'...")
                        
                        for art in articles:
                            art_text = art.inner_text() or ""
                            
                            # Normalize text for robust comparison
                            kw_normalized = keyword.replace("臺", "台").lower()
                            text_normalized = art_text.replace("臺", "台").lower()
                            
                            # 1. Check if the normalized keyword is fully contained in the text in correct order
                            if kw_normalized not in text_normalized:
                                continue
                                
                            # 2. Exclude posts from other schools
                            EXCLUDE_WORDS = ["市北教", "北市大", "台北市立大學", "台北市立教育大學", "市立台北教育大學", "台北大學", "ntpu", "ntu", "台灣大學"]
                            has_exclude = False
                            for ew in EXCLUDE_WORDS:
                                if ew in kw_normalized:
                                    continue
                                if ew in text_normalized:
                                    has_exclude = True
                                    break
                            if has_exclude:
                                print(f"[Threads Playwright] Filtered out post from other university: {art_text[:40]}...")
                                continue
                                
                            link_elem = art.query_selector("a[href*='/post/']")
                            if not link_elem:
                                continue
                                
                            l = link_elem.get_attribute("href") or ""
                            if not l:
                                continue
                                
                            if l.startswith("/"):
                                l = "https://www.threads.net" + l
                            elif "threads.com" in l:
                                l = l.replace("threads.com", "threads.net")
                                
                            if l in seen_urls:
                                continue
                                
                            username = "@unknown"
                            user_m = re.search(r'threads\.net/(@[^/]+)/post', l)
                            if user_m:
                                username = user_m.group(1)
                                
                            # Clean text for preview
                            clean_text = art_text.replace("\n", " ").strip()
                            # Strip out user handle or boilerplate from title if present
                            if username in clean_text:
                                clean_text = clean_text.replace(username, "").strip()
                                
                            # Use actual post snippet as title & excerpt
                            post_title = clean_text[:60] if clean_text else f"Threads 貼文 - {username}"
                            post_excerpt = clean_text[:160] if clean_text else f"從 Threads 搜尋取得之公開貼文。作者: {username}"
                            
                            seen_urls.add(l)
                            results.append({
                                "title": post_title.strip(),
                                "url": l,
                                "source": "Threads",
                                "publish_time": None,
                                "keyword": keyword,
                                "excerpt": post_excerpt,
                                "engagement_count": None
                            })
                    except Exception as select_err:
                        print(f"[Threads Playwright] Selector query failed or timed out: {select_err}")
                except Exception as page_err:
                    print(f"[Threads Playwright] Error loading {q_url}: {page_err}")
                    error_reason = f"page_error: {str(page_err)}"
                    
            browser.close()
            
    except Exception as e:
        print(f"[Threads Playwright] Failed to run Playwright: {e}")
        PLAYWRIGHT_AVAILABLE = False
        error_reason = f"playwright_init_error: {str(e)}"
        
    if not results and not error_reason:
        error_reason = "search_result_empty"
        
    import gc
    gc.collect()
    
    return results, queries, source_used, error_reason

def collect_threads_posts(keyword: str) -> Tuple[dict, List[Dict[str, Any]]]:
    """
    Dedicated Threads collector with detailed metadata and logging.
    """
    from .database import SessionLocal
    from .models import News
    
    trace = {
        "keyword": keyword,
        "official_api_enabled": False,
        "official_api_status": "no_token",
        "fallback_enabled": True,
        "queries": [],
        "raw_result_count": 0,
        "threads_url_count": 0,
        "inserted_count": 0,
        "skipped_duplicate_count": 0,
        "failure_reason": None,
        "sample_results": []
    }
    
    # Priority 1: Official Threads API (if token configured)
    posts, api_status, api_error = fetch_threads_via_official_api(keyword)
    trace["official_api_status"] = api_status
    if api_status != "no_token":
        trace["official_api_enabled"] = True
        
    if posts is not None:
        trace["queries"].append(f"Official API keyword_search?q={keyword}")
        trace["raw_result_count"] = len(posts)
        trace["threads_url_count"] = len(posts)
        source_used = "official_api"
    else:
        # Priority 2: Googlebot scraper (fast, no browser needed)
        print(f"[Threads Collector] Trying Googlebot scraper for '{keyword}'...")
        googlebot_posts = fetch_threads_via_googlebot(keyword)
        if googlebot_posts:
            posts = googlebot_posts
            trace["queries"].append(f"https://www.threads.net/search/?q={keyword}&serp_type=keyword")
            trace["raw_result_count"] = len(posts)
            trace["threads_url_count"] = len(posts)
            source_used = "googlebot_scraper"
            if api_status == "no_token":
                trace["failure_reason"] = "no_api_token_used_googlebot"
        else:
            # Priority 3: Playwright fallback (slow, resource-heavy)
            print(f"[Threads Collector] Googlebot scraper returned 0 results, falling back to Playwright...")
            posts, queries, fallback_source, fallback_reason = fetch_threads_via_fallback(keyword)
            trace["queries"].extend(queries)
            trace["raw_result_count"] = len(posts)
            trace["threads_url_count"] = len(posts)
            source_used = fallback_source
            if fallback_reason:
                trace["failure_reason"] = fallback_reason
            else:
                if api_status == "api_error":
                    trace["failure_reason"] = "api_error"
                elif api_status == "permission_missing":
                    trace["failure_reason"] = "api_permission_missing"
                else:
                    trace["failure_reason"] = "no_api_token"
        
    db = SessionLocal()
    final_posts = []
    try:
        for p in posts or []:
            url_val = p["url"]
            exists = db.query(News).filter(News.url == url_val).first()
            if exists:
                trace["skipped_duplicate_count"] += 1
            else:
                trace["inserted_count"] += 1
                final_posts.append(p)
    finally:
        db.close()
        
    if len(final_posts) == 0:
        if trace["raw_result_count"] == 0:
            if not trace["failure_reason"]:
                if api_status == "no_token":
                    trace["failure_reason"] = "no_api_token"
                elif api_status == "permission_missing":
                    trace["failure_reason"] = "api_permission_missing"
                else:
                    trace["failure_reason"] = "search_result_empty"
        elif trace["threads_url_count"] == 0:
            trace["failure_reason"] = "result_not_threads_url"
        elif trace["skipped_duplicate_count"] > 0:
            trace["failure_reason"] = "duplicate_all"
            
    trace["sample_results"] = [{
        "title": p["title"],
        "url": p["url"],
        "publish_time": str(p["publish_time"]) if p["publish_time"] else None
    } for p in final_posts[:5]]
    
    print(f"--- [Threads Collector Log] ---")
    print(f"Keyword: {keyword}")
    print(f"使用來源: {source_used}")
    for idx, q in enumerate(trace["queries"], 1):
        print(f"實際送出的 query {idx}: {q}")
    print(f"raw_result_count: {trace['raw_result_count']}")
    print(f"threads_url_count: {trace['threads_url_count']}")
    print(f"inserted_count: {trace['inserted_count']}")
    print(f"skipped_duplicate_count: {trace['skipped_duplicate_count']}")
    if len(final_posts) == 0:
        print(f"原因: {trace['failure_reason']}")
    print(f"-------------------------------")
    
    return trace, final_posts

def fetch_social_via_google_news(keyword: str) -> List[Dict[str, Any]]:
    """
    Uses Google News RSS to find PTT, Threads, Instagram, and Dcard posts
    mentioning the keyword within the past 7 days.
    
    Strategy: search for keyword + platform name. Google News indexes PTT/Threads/Dcard
    and returns them in regular RSS results. We filter by URL domain to identify social posts.
    """
    import email.utils

    SOCIAL_DOMAIN_MAP = {
        "ptt.cc": "PTT",
        "pttweb.cc": "PTT",
        "instagram.com": "Instagram",
        "dcard.tw": "Dcard",
        "threads.net": "Threads",
        "threads.com": "Threads",
    }

    items = []
    seen_urls = set()
    cutoff = datetime.now() - timedelta(days=30)

    # Search queries: keyword + platform name (helps Google surface those results)
    queries = [
        f"{keyword} site:ptt.cc when:30d",
        f"{keyword} site:dcard.tw/f/ntue when:30d",
        f"{keyword} site:threads.net when:30d",
        f"{keyword} instagram when:30d",
    ]

    for query in queries:
        encoded = urllib.parse.quote(query)
        rss_url = (
            f"https://news.google.com/rss/search"
            f"?q={encoded}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        )
        try:
            response = httpx.get(rss_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }, timeout=10.0)
            response.raise_for_status()

            root = ET.fromstring(response.content)
            for item in root.findall(".//item")[:30]:
                link = item.findtext("link", "")
                title = item.findtext("title", "")
                pub_date_text = item.findtext("pubDate", "")

                if not link or not title:
                    continue

                # Resolve redirect URL to get direct domain/URL info
                resolved_link = resolve_google_news_link(link)
                link_lower = resolved_link.lower()
                source = None
                for domain, src_name in SOCIAL_DOMAIN_MAP.items():
                    if domain in link_lower:
                        source = src_name
                        break

                if source is None:
                    continue  # Not a social post link

                # Dedup
                if resolved_link in seen_urls:
                    continue

                # Must be a real post (not a board/profile page)
                if not is_real_social_post(resolved_link):
                    continue

                # Title relevance check (for PTT/Threads/IG — Dcard board URL is self-validating)
                if source != "Dcard" and not title_mentions_ntue(title):
                    title_safe = title[:50].encode('utf-8', errors='ignore').decode('utf-8')
                    print(f"[Google Social] Skipping irrelevant: {title_safe}")
                    continue

                # Determine actual publish time of the post
                publish_time = None
                if source == "Dcard":
                    dcard_meta = fetch_dcard_metadata(resolved_link)
                    if dcard_meta["publishedAt"]:
                        publish_time = dcard_meta["publishedAt"]
                    if dcard_meta["title"]:
                        title = dcard_meta["title"]
                elif source == "PTT":
                    publish_time = fetch_ptt_published_time(resolved_link)
                elif source == "Threads":
                    if pub_date_text:
                        try:
                            import email.utils
                            publish_time = email.utils.parsedate_to_datetime(pub_date_text)
                        except Exception:
                            pass
                elif source == "Instagram":
                    pass

                # Filter to past 30 days (only if publish_time is parsed and NOT Threads)
                if source != "Threads" and publish_time is not None:
                    if publish_time < cutoff:
                        title_safe = title[:50].encode('utf-8', errors='ignore').decode('utf-8')
                        print(f"[Google Social] Skipping old ({(datetime.now()-publish_time).days}d): {title_safe}")
                        continue

                # Clean title (strip " - PTT" etc)
                clean_title = title
                if " - " in title:
                    clean_title = title.rsplit(" - ", 1)[0]

                seen_urls.add(resolved_link)
                items.append({
                    "title": clean_title.strip(),
                    "url": resolved_link,
                    "source": source,
                    "publish_time": publish_time,
                    "keyword": keyword,
                })
        except Exception as e:
            err_safe = str(e).encode('utf-8', errors='ignore').decode('utf-8')
            print(f"[Google Social] Error searching: {err_safe}")

    print(f"[Google Social] Found {len(items)} social posts via Google News for keyword '{keyword}'")
    return items


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

    # First fetch from Google News RSS for better coverage of PTT/Threads/Instagram/Dcard
    print(f"[Social Scraper] Fetching from Google News RSS first...")
    try:
        items = fetch_social_via_google_news(keyword)
    except Exception as e:
        print(f"[Social Scraper] Google News search failed: {e}")
        items = []
    seen_urls = {item["url"] for item in items}
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Forwarded-For": "114.36.210.88",
        "X-Real-IP": "114.36.210.88",
        "Client-IP": "114.36.210.88",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    def yahoo_search(query: str, use_btf: bool = False) -> list:
        """Return list of (url, title, date_text) from Yahoo search.
        use_btf=True appends &btf=w to restrict to past-week results.
        """
        encoded = urllib.parse.quote(query)
        btf_param = "&btf=w" if use_btf else ""
        
        urls_to_try = [
            f"https://tw.search.yahoo.com/search?p={encoded}{btf_param}",
            f"https://hk.search.yahoo.com/search?p={encoded}{btf_param}",
            f"https://search.yahoo.com/search?p={encoded}{btf_param}"
        ]
        
        for search_url in urls_to_try:
            try:
                req = urllib.request.Request(search_url, headers=headers)
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    html_text = resp.read().decode("utf-8", errors="ignore")
                if 'href="https://r.search.yahoo.com/' not in html_text:
                    continue
                segments = html_text.split('href="https://r.search.yahoo.com/')
                results = []
                for seg in segments[1:]:
                    ru_match = re.search(r'RU=([^/"]+)/', seg)
                    if not ru_match:
                        continue
                    direct_url = urllib.parse.unquote(ru_match.group(1))
                    
                    # --- Multi-strategy title extractor ---
                    # Strategy 1: Look for h3 tag (most reliable on Yahoo TW/HK)
                    title = ""
                    h3_m = re.search(r'<h3[^>]*>(.*?)</h3>', seg[:3000], re.DOTALL)
                    if h3_m:
                        title = re.sub(r'<[^>]+>', '', h3_m.group(1))
                        title = htmllib.unescape(title).strip()
                    
                    # Strategy 2: aria-label if h3 is missing/empty
                    if not title or len(title) < 3:
                        aria_m = re.search(r'aria-label="([^"]{5,})"', seg)
                        if aria_m:
                            candidate = htmllib.unescape(aria_m.group(1))
                            # Reject URL-like strings
                            if not re.search(r'[_=&%]{3,}', candidate):
                                title = candidate.strip()
                    
                    # Strategy 3: compTitle / search snippet text
                    if not title or len(title) < 3:
                        comp_m = re.search(r'class="[^"]*compTitle[^"]*"[^>]*>(.*?)</(?:h3|h2|div|span)>', seg[:3000], re.DOTALL)
                        if comp_m:
                            title = re.sub(r'<[^>]+>', '', comp_m.group(1))
                            title = htmllib.unescape(title).strip()
                    
                    # Clean up any remaining HTML artifacts from title
                    # Remove Yahoo tracking params (_ylt, _ylu, _ylv, RK=, RS=)
                    title = re.sub(r'_y(?:lt|lu|lv)=[^;\s"<]+', '', title)
                    title = re.sub(r'RK=\d+[^\s"<]*', '', title)
                    title = re.sub(r'RS=[^\s"<]+', '', title)
                    # Remove URL-encoded garbage (sequences of %XX patterns)
                    title = re.sub(r'(?:%[0-9a-fA-F]{2}){3,}[^\s]*', '', title)
                    # Remove remaining HTML tags
                    title = re.sub(r'<[^>]+>', ' ', title)
                    title = htmllib.unescape(title)
                    title = re.sub(r'\s+', ' ', title).strip()
                    
                    date_m = re.search(r'<span class="fc-smoke">([^<]+)</span>', seg[:2000])
                    date_text = date_m.group(1).strip() if date_m else None
                    results.append((direct_url, title, date_text))
                
                if results:
                    print(f"[Social Scraper] Yahoo search succeeded using: {search_url} (Found {len(results)} results)")
                    return results
            except Exception as e:
                print(f"[Social Scraper] Yahoo search failed for {search_url}: {e}")
                
        return []

    def try_add(url: str, title: str, source: str, kw: str, date_text: str = None,
                require_relevance: bool = False):
        """Validate and add an article to items list."""
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
            title_safe = title[:50].encode('utf-8', errors='ignore').decode('utf-8')
            print(f"[Social Scraper] Skipping irrelevant: {title_safe}")
            return
        
        # Determine actual publish time of the post
        publish_time = None
        if source == "Dcard":
            dcard_meta = fetch_dcard_metadata(url)
            if dcard_meta["publishedAt"]:
                publish_time = dcard_meta["publishedAt"]
            if dcard_meta["title"]:
                title = dcard_meta["title"]
        elif source == "PTT":
            publish_time = fetch_ptt_published_time(url)
        elif source == "Threads":
            pass  # publish_time will use date_text fallback or datetime.now()
        elif source == "Instagram":
            pass

        # Fallback to Yahoo search result's date_text if detailed page fetch fails
        if publish_time is None and date_text:
            try:
                publish_time = parse_yahoo_date(date_text)
            except Exception:
                pass
                
        # Final fallback: default to current time to avoid None (shows as 1970/1/1 or Time Unknown)
        if publish_time is None:
            publish_time = datetime.now()

        # Filter to past 30 days (only if publish_time is parsed and NOT Threads)
        if source != "Threads" and publish_time is not None:
            age_days = (datetime.now() - publish_time).days
            if age_days > 30:
                title_safe = title[:50].encode('utf-8', errors='ignore').decode('utf-8')
                print(f"[Social Scraper] Skipping old post ({age_days}d): {title_safe}")
                return
        
        seen_urls.add(url)
        items.append({
            "title": title.strip(),
            "url": url,
            "source": source,
            "publish_time": publish_time,
            "keyword": kw,
        })

    import random

    # ── 1. Dcard: search dedicated NTUE board only ──────────────────────────
    print(f"[Social Scraper] Searching Dcard NTUE board...")
    for url, title, date_text in yahoo_search("site:dcard.tw/f/ntue"):
        if "dcard.tw" not in url.lower():
            continue
        try_add(url, title, "Dcard", keyword, date_text=date_text, require_relevance=False)
    time.sleep(2.0 + random.random() * 2.0)

    # ── 2. Threads: Yahoo Search site:threads.net booster ──────────────────────
    print(f"[Social Scraper] Running Yahoo search booster for Threads posts related to '{keyword}'...")
    try:
        kw_normalized = keyword.replace("臺", "台").lower()
        EXCLUDE_WORDS = ["市北教", "北市大", "台北市立大學", "台北市立教育大學", "市立台北教育大學", "台北大學", "ntpu", "ntu", "台灣大學"]
        for url, title, date_text in yahoo_search(f"site:threads.net {keyword}"):
            url_lower = url.lower()
            # Must be a real Threads post URL (not homepage or profile)
            if "threads.net" not in url_lower and "threads.com" not in url_lower:
                continue
            if "/post/" not in url_lower and "/t/" not in url_lower:
                continue
            
            # Clean up the title from HTML artifacts
            # titles from yahoo_search may contain URL-encoded segments or HTML garbage
            clean_title = title
            # Remove URL-encoded fragments (e.g. %2ft%2fXXX/RK=2/RS=...)
            clean_title = re.sub(r'%[0-9a-fA-F]{2}[\w%/=\-\.]*', '', clean_title)
            clean_title = re.sub(r'RK=\d+.*', '', clean_title)
            # Remove generic placeholder words
            clean_title = clean_title.replace("www.threads.net", "").replace("threads.net", "").replace("Threads", "").strip()
            # Strip HTML tags if any remain
            clean_title = re.sub(r'<[^>]+>', ' ', clean_title)
            clean_title = re.sub(r'\s+', ' ', clean_title).strip()
            
            # If title has actual content and contains the keyword, use it directly
            # If title is too short/empty, use a default
            text_normalized = clean_title.replace("臺", "台").lower()
            
            # Check for exclusion words in title (only if title has content)
            has_exclude = False
            if clean_title:
                for ew in EXCLUDE_WORDS:
                    if ew in kw_normalized:  # Don't exclude if ew is part of our keyword
                        continue
                    if ew in text_normalized:
                        has_exclude = True
                        break
            if has_exclude:
                continue
            
            # Build final post title (use what we have, or fallback)
            post_title = clean_title[:80] if len(clean_title) > 5 else f"Threads 貼文 - {url.split('/')[-1][:20]}"
            
            try_add(url, post_title, "Threads", keyword, date_text=date_text, require_relevance=False)
    except Exception as yahoo_threads_err:
        print(f"[Social Scraper] Yahoo search Threads booster error: {yahoo_threads_err}")
    time.sleep(2.0 + random.random() * 2.0)

    # ── 3. Threads: Dedicated official API & Playwright crawler ──────────────────
    print(f"[Social Scraper] Running dedicated Threads collector for '{keyword}'...")
    try:
        trace_data, threads_posts = collect_threads_posts(keyword)
        for p in threads_posts:
            if p["url"] not in seen_urls:
                seen_urls.add(p["url"])
                items.append(p)
    except Exception as threads_err:
        print(f"[Social Scraper] Error in Threads collector: {threads_err}")
    time.sleep(2.0 + random.random() * 2.0)

    # ── 4. PTT: keyword + ptt + btf=w, require title relevance ─────────────
    print(f"[Social Scraper] Searching PTT for '{keyword}'...")
    for url, title, date_text in yahoo_search(f"{keyword} ptt", use_btf=True):
        if "ptt.cc" not in url.lower() and "pttweb.cc" not in url.lower():
            continue
        try_add(url, title, "PTT", keyword, date_text=date_text, require_relevance=True)
    time.sleep(2.0 + random.random() * 2.0)

    # ── 5. Instagram: keyword + instagram + btf=w, require title relevance ───
    print(f"[Social Scraper] Searching Instagram for '{keyword}'...")
    for url, title, date_text in yahoo_search(f"{keyword} instagram", use_btf=True):
        if "instagram.com" not in url.lower():
            continue
        try_add(url, title, "Instagram", keyword, date_text=date_text, require_relevance=True)

    print(f"[Social Scraper] Found {len(items)} valid social posts for keyword '{keyword}'")
    return items




