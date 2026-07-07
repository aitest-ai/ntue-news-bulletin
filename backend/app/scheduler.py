from datetime import datetime
import pytz

from .database import SessionLocal
from . import models, parser


LAST_FETCH_TRACE = {
    "status": "never_run",
    "timestamp": None,
    "total_keywords": 0,
    "details": [],
    "error": None
}

from threading import Lock
FETCH_LOCK = Lock()

def fetch_all_keywords_news():
    if not FETCH_LOCK.acquire(blocking=False):
        print(f"[{datetime.now()}] Fetch already in progress. Skipping.")
        return 0
    
    global LAST_FETCH_TRACE
    LAST_FETCH_TRACE = {
        "status": "running",
        "timestamp": str(datetime.now()),
        "total_keywords": 0,
        "details": [],
        "error": None
    }
    db = SessionLocal()
    try:
        keywords = db.query(models.Keyword).all()
        if not keywords:
            default_words = [
                "國立臺北教育大學",
                "國北教大",
                "北教大",
                "NTUE",
                "National Taipei University of Education"
            ]
            for word in default_words:
                db.add(models.Keyword(word=word))
            db.commit()
            keywords = db.query(models.Keyword).all()
            
        LAST_FETCH_TRACE["total_keywords"] = len(keywords)
        print(f"[{datetime.now()}] Starting scheduled news fetch for {len(keywords)} keywords...")
        
        total_new = 0
        for kw in keywords:
            # 1. Fetch traditional news
            items = parser.fetch_google_news_rss(kw.word)
            
            # 2. Fetch social/forum posts using Yahoo Search scraper
            social_items = parser.fetch_social_posts(kw.word)
            
            all_items = items + social_items
            
            LAST_FETCH_TRACE["details"].append({
                "keyword": kw.word,
                "traditional_fetched": len(items),
                "social_fetched": len(social_items)
            })
            
            import hashlib
            for item in all_items:
                # Unique key: prioritizes url, fallbacks to hash of platform + title + keyword if invalid
                url_val = item.get("url")
                if url_val and isinstance(url_val, str) and url_val.strip().lower().startswith("http"):
                    unique_url = url_val.strip()
                else:
                    platform = item.get("source", "Social")
                    title_val = item.get("title", "")
                    kw_val = item.get("keyword", "")
                    raw_str = f"{platform}:{title_val}:{kw_val}"
                    h = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()
                    unique_url = f"hash://{platform}/{h}"

                exists = db.query(models.News).filter(models.News.url == unique_url).first()
                if not exists:
                    news_entry = models.News(
                        title=item["title"],
                        url=unique_url,
                        source=item["source"],
                        publish_time=item["publish_time"],
                        keyword=item["keyword"],
                        crawled_at=datetime.utcnow()
                    )
                    db.add(news_entry)
                    total_new += 1
            db.commit()

            
        print(f"[{datetime.now()}] Finished scheduled news fetch. Saved {total_new} new articles.")
        LAST_FETCH_TRACE["status"] = "success"
        LAST_FETCH_TRACE["saved_articles"] = total_new
        
        # Trigger daily news email dispatch
        try:
            tz = pytz.timezone("Asia/Taipei")
            now_local = datetime.now(tz)
            start_of_today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            news_today = db.query(models.News).filter(
                models.News.publish_time >= start_of_today
            ).all()
            
            is_empty_today = len(news_today) == 0
            if is_empty_today:
                # Fetch latest 3 news and 3 social posts
                latest_news = db.query(models.News).filter(
                    models.News.source.notin_(["Dcard", "PTT", "Threads", "Instagram"])
                ).order_by(models.News.publish_time.desc()).limit(3).all()
                
                latest_social = db.query(models.News).filter(
                    models.News.source.in_(["Dcard", "PTT", "Threads", "Instagram"])
                ).order_by(models.News.publish_time.desc()).limit(3).all()
                
                news_today = latest_news + latest_social
            
            date_str = now_local.strftime("%Y/%m/%d")
            from .mailer import send_daily_news_email
            send_daily_news_email(news_today, date_str, is_empty_today=is_empty_today)
        except Exception as mail_err:
            print(f"Error preparing or sending news email: {mail_err}")
            LAST_FETCH_TRACE["email_dispatch_error"] = str(mail_err)

        return total_new
    except Exception as e:
        print(f"Error in scheduled news fetch: {e}")
        LAST_FETCH_TRACE["status"] = "failed"
        LAST_FETCH_TRACE["error"] = str(e)
        db.rollback()
        return 0
    finally:
        db.close()
        FETCH_LOCK.release()

def init_default_jobs(db):
    """
    Initialize default scheduled jobs in the database if empty.
    """
    job_count = db.query(models.ScheduledJob).count()
    if job_count == 0:
        fetch_times = [
            ("7", "30"), ("8", "0"), ("8", "30"),
            ("9", "0"), ("9", "30"), ("10", "0"),
            ("16", "0"), ("16", "30"), ("17", "0"),
            ("17", "30"), ("18", "0")
        ]
        
        for h, m in fetch_times:
            job_id = f"news_fetch_{h}_{m}"
            job_name = f"自動抓取新聞 {h}:{m.zfill(2)}"
            new_job = models.ScheduledJob(
                id=job_id,
                name=job_name,
                hour=int(h),
                minute=int(m),
                paused=0
            )
            db.add(new_job)
        db.commit()
        print(f"Initialized {len(fetch_times)} default jobs in DB.")
