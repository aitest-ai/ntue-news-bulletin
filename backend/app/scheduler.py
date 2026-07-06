from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import pytz

from .database import SessionLocal
from . import models, parser

scheduler = BackgroundScheduler()

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
            now = datetime.now(tz)
            
            # Localize dates in Taipei timezone first
            start_of_today = tz.localize(datetime(now.year, now.month, now.day, 0, 0, 0))
            end_of_today = tz.localize(datetime(now.year, now.month, now.day, 23, 59, 59))
            
            # Convert to UTC naive datetimes to match SQLite database datetime formats
            utc_start = start_of_today.astimezone(pytz.utc).replace(tzinfo=None)
            utc_end = end_of_today.astimezone(pytz.utc).replace(tzinfo=None)
            
            news_today = db.query(models.News).filter(
                models.News.publish_time >= utc_start,
                models.News.publish_time <= utc_end
            ).order_by(models.News.publish_time.desc()).all()

            
            date_str = now.strftime("%Y/%m/%d")
            from .mailer import send_daily_news_email
            send_daily_news_email(news_today, date_str)
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

def start_scheduler():
    # Ensure default keywords exist in database before starting
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
            print("Default keywords seeded in database.")
    except Exception as e:
        print(f"Error seeding database keywords on startup: {e}")
        db.rollback()
    finally:
        db.close()

    # Timezone Asia/Taipei
    tz = pytz.timezone("Asia/Taipei")

    # Cron timings: 
    # Morning: 07:30, 08:00, 08:30, 09:00, 09:30, 10:00 Taipei time
    # Evening: 16:00, 16:30, 17:00, 17:30, 18:00 Taipei time
    fetch_times = [
        ("7", "30"),
        ("8", "0"),
        ("8", "30"),
        ("9", "0"),
        ("9", "30"),
        ("10", "0"),
        ("16", "0"),
        ("16", "30"),
        ("17", "0"),
        ("17", "30"),
        ("18", "0")
    ]
    
    for h, m in fetch_times:
        job_id = f"news_fetch_{h}_{m}"
        job_name = f"自動抓取新聞 {h}:{m.zfill(2)}"
        scheduler.add_job(
            fetch_all_keywords_news,
            CronTrigger(hour=h, minute=m, timezone=tz),
            id=job_id,
            name=job_name,
            replace_existing=True
        )
        
    scheduler.start()
    print(f"APScheduler workers started. Registered {len(fetch_times)} daily cron triggers.")
