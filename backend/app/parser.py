import httpx
import xml.etree.ElementTree as ET
from datetime import datetime
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
