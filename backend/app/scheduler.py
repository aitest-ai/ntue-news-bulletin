from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import pytz

from .database import SessionLocal
from . import models, parser

scheduler = BackgroundScheduler()

def fetch_all_keywords_news():
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
            
        print(f"[{datetime.now()}] Starting scheduled news fetch for {len(keywords)} keywords...")
        
        total_new = 0
        for kw in keywords:
            items = parser.fetch_google_news_rss(kw.word)
            for item in items:
                # Database-agnostic query-and-insert deduplication
                exists = db.query(models.News).filter(models.News.url == item["url"]).first()
                if not exists:
                    news_entry = models.News(
                        title=item["title"],
                        url=item["url"],
                        source=item["source"],
                        publish_time=item["publish_time"],
                        keyword=item["keyword"]
                    )
                    db.add(news_entry)
                    total_new += 1
            db.commit()
            
        print(f"[{datetime.now()}] Finished scheduled news fetch. Saved {total_new} new articles.")
        
        # Trigger daily news email dispatch
        try:
            tz = pytz.timezone("Asia/Taipei")
            now = datetime.now(tz)
            start_of_today = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=tz)
            end_of_today = datetime(now.year, now.month, now.day, 23, 59, 59, tzinfo=tz)
            
            news_today = db.query(models.News).filter(
                models.News.publish_time >= start_of_today,
                models.News.publish_time <= end_of_today
            ).order_by(models.News.publish_time.desc()).all()
            
            date_str = now.strftime("%Y/%m/%d")
            from .mailer import send_daily_news_email
            send_daily_news_email(news_today, date_str)
        except Exception as mail_err:
            print(f"Error preparing or sending news email: {mail_err}")

        return total_new
    except Exception as e:
        print(f"Error in scheduled news fetch: {e}")
        db.rollback()
        return 0
    finally:
        db.close()

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
