import httpx
import xml.etree.ElementTree as ET
from datetime import datetime
import email.utils
import urllib.parse
from typing import List, Dict, Any

def resolve_google_news_link(url: str) -> str:
    """
    Sends a request to follow Google News redirect and returns the original target URL.
    Falls back to the original URL if a timeout or connection issue occurs.
    """
    if not url or "news.google.com" not in url:
        return url
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        # Use httpx Client to follow redirects
        # Set a short timeout (3.0 seconds) to prevent the crawler from hanging too long
        with httpx.Client(follow_redirects=True, headers=headers, timeout=3.0) as client:
            # Try HEAD first as it is lightweight
            response = client.head(url)
            # If the site blocks HEAD (405, 403, etc.), fall back to GET
            if response.status_code in [403, 404, 405]:
                response = client.get(url)
            
            final_url = str(response.url)
            print(f"[Parser] Resolved: {url[:50]}... -> {final_url[:70]}")
            return final_url
    except Exception as e:
        # In case of timeout or other network issues, fall back to the google news redirect URL
        print(f"[Parser] Failed to resolve redirect for {url[:50]}: {e}")
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
