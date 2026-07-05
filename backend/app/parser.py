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

def fetch_social_posts(keyword: str) -> List[Dict[str, Any]]:
    """
    Searches Yahoo for Dcard, PTT, Threads, IG, and FB posts mentioning the keyword.
    Parses dates and filters out posts older than 7 days, as well as non-posts.
    """
    import html
    
    # Only search Dcard, PTT, Threads, Facebook, Instagram
    search_queries = [
        f'"{keyword}" dcard',
        f'"{keyword}" ptt',
        f'"{keyword}" threads',
        f'"{keyword}" facebook',
        f'"{keyword}" instagram'
    ]
    
    items = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    for query in search_queries:
        encoded_query = urllib.parse.quote(query)
        # Append &btf=w to restrict Yahoo Search results to the past week (7 days)
        url = f"https://tw.search.yahoo.com/search?p={encoded_query}&btf=w"
        
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8.0) as response:
                html_text = response.read().decode('utf-8', errors='ignore')
                
            # Split by redirect link prefix to isolate result blocks cleanly
            segments = html_text.split('href="https://r.search.yahoo.com/')
            
            for seg in segments[1:]:
                # Extract direct URL from RU parameter
                ru_match = re.search(r'RU=([^/"]+)/', seg)
                if not ru_match:
                    continue
                direct_url = urllib.parse.unquote(ru_match.group(1))
                
                # Verify it is one of our target social domains
                is_social = any(d in direct_url.lower() for d in [
                    "dcard.tw", "ptt.cc", "pttweb.cc", "threads.net", 
                    "threads.com", "instagram.com", "facebook.com"
                ])
                if not is_social:
                    continue
                    
                # Exclude duplicate URLs in current fetch batch
                if any(item["url"] == direct_url for item in items):
                    continue
                    
                # ONLY capture actual posts, NOT board/profile homepages
                if not is_real_social_post(direct_url):
                    continue
                    
                # Title is in aria-label attribute of the link
                title_match = re.search(r'aria-label="([^"]+)"', seg)
                if not title_match:
                    continue
                clean_title = html.unescape(title_match.group(1))
                
                # Date tag is in span with class fc-smoke nearby
                date_match = re.search(r'<span class="fc-smoke">([^<]+)</span>', seg[:1500])
                date_text = date_match.group(1).strip() if date_match else "None"
                
                # Parse date and filter out posts older than 7 days
                publish_time = parse_yahoo_date(date_text)
                if (datetime.now() - publish_time).days > 7:
                    # Skip posts older than 1 week
                    continue
                    
                # Set appropriate source name based on URL
                source = "Social Media"
                url_lower = direct_url.lower()
                if "dcard.tw" in url_lower:
                    source = "Dcard"
                elif "ptt.cc" in url_lower or "pttweb.cc" in url_lower:
                    source = "PTT"
                elif "threads.net" in url_lower or "threads.com" in url_lower:
                    source = "Threads"
                elif "facebook.com" in url_lower:
                    source = "Facebook"
                elif "instagram.com" in url_lower:
                    source = "Instagram"
                    
                items.append({
                    "title": clean_title.strip(),
                    "url": direct_url,
                    "source": source,
                    "publish_time": publish_time,
                    "keyword": keyword
                })
        except Exception as e:
            print(f"[Social Scraper] Error searching '{query}' on Yahoo: {e}")
            
    print(f"[Social Scraper] Found {len(items)} social posts (newer than 1 week) for keyword '{keyword}'")
    return items

