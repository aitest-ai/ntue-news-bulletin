from datetime import datetime
import hashlib
import pytz

from .database import SessionLocal
from . import models
from .task_pipeline import collect_keyword


LAST_FETCH_TRACE = {
    "status": "never_run",
    "timestamp": None,
    "total_keywords": 0,
    "details": [],
    "error": None,
}

from threading import Lock
FETCH_LOCK = Lock()


def _unique_url(item):
    url_val = item.get("url")
    if url_val and isinstance(url_val, str) and url_val.strip().lower().startswith("http"):
        return url_val.strip()
    platform = item.get("source", "Unknown")
    raw_str = f"{platform}:{item.get('title','')}:{item.get('keyword','')}"
    digest = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()
    return f"hash://{platform}/{digest}"


def fetch_all_keywords_news():
    if not FETCH_LOCK.acquire(blocking=False):
        print(f"[{datetime.now()}] Fetch already in progress. Skipping.")
        return 0

    global LAST_FETCH_TRACE
    LAST_FETCH_TRACE = {
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "total_keywords": 0,
        "details": [],
        "error": None,
    }

    db = SessionLocal()
    try:
        keywords = db.query(models.Keyword).all()
        if not keywords:
            for word in [
                "國立臺北教育大學",
                "國北教大",
                "北教大",
                "NTUE",
                "National Taipei University of Education",
            ]:
                db.add(models.Keyword(word=word))
            db.commit()
            keywords = db.query(models.Keyword).all()

        LAST_FETCH_TRACE["total_keywords"] = len(keywords)
        total_new = 0

        for kw in keywords:
            result = collect_keyword(kw.word)
            LAST_FETCH_TRACE["details"].append({
                "keyword": kw.word,
                "status": result["status"],
                "count": result["count"],
                "tasks": result["tasks"],
            })

            for item in result["items"]:
                unique_url = _unique_url(item)
                exists = db.query(models.News).filter(models.News.url == unique_url).first()
                if exists:
                    continue

                publish_time = item.get("publish_time")
                if not publish_time or getattr(publish_time, "year", 1970) <= 1971:
                    publish_time = datetime.utcnow()

                db.add(models.News(
                    title=item.get("title", "未命名內容"),
                    url=unique_url,
                    source=item.get("source", "Unknown"),
                    publish_time=publish_time,
                    keyword=item.get("keyword", kw.word),
                    crawled_at=datetime.utcnow(),
                ))
                total_new += 1

            db.commit()

        LAST_FETCH_TRACE["status"] = "success"
        LAST_FETCH_TRACE["saved_articles"] = total_new

        try:
            tz = pytz.timezone("Asia/Taipei")
            now_local = datetime.now(tz)
            start_of_today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            news_today = db.query(models.News).filter(models.News.publish_time >= start_of_today).all()
            is_empty_today = len(news_today) == 0
            if is_empty_today:
                latest_news = db.query(models.News).filter(
                    models.News.source.notin_(["Dcard", "PTT", "Threads", "Instagram"])
                ).order_by(models.News.publish_time.desc()).limit(3).all()
                latest_social = db.query(models.News).filter(
                    models.News.source.in_(["Dcard", "PTT", "Threads", "Instagram"])
                ).order_by(models.News.publish_time.desc()).limit(3).all()
                news_today = latest_news + latest_social

            from .mailer import send_daily_news_email
            send_daily_news_email(news_today, now_local.strftime("%Y/%m/%d"), is_empty_today=is_empty_today)
        except Exception as mail_err:
            LAST_FETCH_TRACE["email_dispatch_error"] = str(mail_err)

        print(f"[{datetime.now()}] Task pipeline complete. Saved {total_new} new items.")
        return total_new
    except Exception as e:
        db.rollback()
        LAST_FETCH_TRACE["status"] = "failed"
        LAST_FETCH_TRACE["error"] = str(e)
        print(f"Error in scheduled news fetch: {e}")
        return 0
    finally:
        db.close()
        FETCH_LOCK.release()


def init_default_jobs(db):
    if db.query(models.ScheduledJob).count() == 0:
        fetch_times = [
            ("7", "30"), ("8", "0"), ("8", "30"),
            ("9", "0"), ("9", "30"), ("10", "0"),
            ("16", "0"), ("16", "30"), ("17", "0"),
            ("17", "30"), ("18", "0"),
        ]
        for h, m in fetch_times:
            db.add(models.ScheduledJob(
                id=f"news_fetch_{h}_{m}",
                name=f"自動抓取新聞 {h}:{m.zfill(2)}",
                hour=int(h),
                minute=int(m),
                paused=0,
            ))
        db.commit()
