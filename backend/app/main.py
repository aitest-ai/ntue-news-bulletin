from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from apscheduler.triggers.cron import CronTrigger
import pytz
from typing import List

from .database import engine, Base, get_db, SessionLocal
from . import models, schemas, scheduler, auth
from .parser import fetch_google_news_rss
from .config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure SQLite tables exist
    Base.metadata.create_all(bind=engine)
    
    # Auto install playwright chromium in a background thread to avoid blocking health checks
    import threading
    def bg_install_playwright():
        import subprocess
        import sys
        try:
            print("[Playwright Startup] Running background auto-install of Chromium...")
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
            print("[Playwright Startup] Chromium background auto-installation completed.")
        except Exception as install_err:
            print(f"[Playwright Startup] Warning: Background Chromium auto-installation failed: {install_err}")
            
    threading.Thread(target=bg_install_playwright, daemon=True).start()
    
    # Run automatic SQLite migration if crawled_at column is missing
    from sqlalchemy import text
    db_mig = SessionLocal()
    try:
        db_mig.execute(text("SELECT crawled_at FROM news LIMIT 1"))
    except Exception:
        print("Column 'crawled_at' does not exist in 'news' table. Altering table...")
        db_mig.rollback()
        try:
            db_mig.execute(text("ALTER TABLE news ADD COLUMN crawled_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
            db_mig.commit()
            print("Successfully added 'crawled_at' column to 'news' table.")
        except Exception as migration_err:
            print(f"Error altering table 'news': {migration_err}")
            db_mig.rollback()
    finally:
        db_mig.close()
    
    # Seed default keywords synchronously before starting the scheduler
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
            print("Default keywords successfully seeded in database.")
    except Exception as e:
        print(f"Error seeding database keywords on startup: {e}")
        db.rollback()
    finally:
        db.close()

    # Start APScheduler background tasks
    scheduler.start_scheduler()
    
    # NOTE: Do NOT auto-fetch on startup. The scheduler cron jobs will handle populating data.
    # Auto-fetching on cold start causes Render free-tier to run out of resources and restart endlessly.
        
    yield
    # Safely shutdown APScheduler on app termination
    scheduler.scheduler.shutdown()

app = FastAPI(
    title="NTUE Bulletin Board API",
    description="Password-protected backend API for the NTUE News Bulletin Board",
    version="1.0",
    lifespan=lifespan
)

# Enable CORS for frontend dashboard communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://ntue-news-bulletin.vercel.app"
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/auth/login", response_model=schemas.LoginResponse)
def login(req: schemas.LoginRequest):
    """
    Authenticate access using the system password.
    Returns a JWT access token if successful.
    """
    if req.password != settings.ADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="密碼錯誤，拒絕存取系統！"
        )
    
    token = auth.create_access_token(data={"sub": "admin"})
    return {"access_token": token, "token_type": "bearer"}

from sqlalchemy import func

@app.get("/api/news", response_model=schemas.NewsResponse)
def read_news(
    skip: int = 0,
    limit: int = 10,
    keyword: str = None,
    db: Session = Depends(get_db),
    user: str = Depends(auth.verify_token)
):
    """
    Fetch paginated news collected from RSS. (Guarded by Password JWT)
    """
    try:
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import or_, and_
        
        query = db.query(models.News)
        if keyword:
            query = query.filter(models.News.keyword == keyword)
            
        # Try using timezone-aware UTC datetime
        now = datetime.now(timezone.utc)
        one_month_ago = now - timedelta(days=30)
        SOCIAL_SOURCES = ["Dcard", "PTT", "Threads", "Instagram"]
        
        is_social = models.News.source.in_(SOCIAL_SOURCES)
        is_news = ~models.News.source.in_(SOCIAL_SOURCES)
        
        social_valid_crawled = and_(
            models.News.crawled_at.isnot(None),
            models.News.crawled_at >= one_month_ago
        )
        social_valid_created = and_(
            models.News.crawled_at.is_(None),
            models.News.created_at >= one_month_ago
        )
        
        social_filter = and_(
            is_social,
            or_(social_valid_crawled, social_valid_created)
        )
        
        query = query.filter(or_(is_news, social_filter))
        
        from sqlalchemy import case
        threads_priority = case(
            (models.News.source == "Threads", 1),
            else_=0
        ).desc()
        
        total = query.count()
        items = query.order_by(
            threads_priority,
            func.coalesce(models.News.publish_time, models.News.crawled_at, models.News.created_at).desc()
        ).offset(skip).limit(limit).all()
        return {"total": total, "items": items}
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        print(f"Error in read_news: {err_msg}")
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}\n{err_msg}")

@app.post("/api/news/fetch")
def trigger_fetch(background_tasks: BackgroundTasks, user: str = Depends(auth.verify_token)):
    """
    Manually triggers RSS fetch of news for all active keywords in the background. (Guarded by Password JWT)
    """
    background_tasks.add_task(scheduler.fetch_all_keywords_news)
    return {"message": "已在背景啟動新聞與輿情抓取任務，請於 30 秒至 1 分鐘後重新整理網頁！", "new_articles_count": 0}

@app.get("/api/news/fetch-trace")
def get_fetch_trace(user: str = Depends(auth.verify_token)):
    """
    Retrieve the status and trace details of the last background news fetch task. (Guarded by Password JWT)
    """
    return scheduler.LAST_FETCH_TRACE

@app.post("/api/news/cleanup-social")
def cleanup_social(db: Session = Depends(get_db), user: str = Depends(auth.verify_token)):
    """
    Deletes all social posts from the database to allow clean recrawling. (Guarded by Password JWT)
    """
    SOCIAL_SOURCES = ["Dcard", "PTT", "Threads", "Facebook", "Instagram", "Social Media"]  # Facebook kept here to clean up old entries
    deleted_count = db.query(models.News).filter(models.News.source.in_(SOCIAL_SOURCES)).delete(synchronize_session=False)
    db.commit()
    return {"message": f"成功清理 {deleted_count} 筆舊社群貼文！"}

@app.post("/api/test-email")
def test_email(user: str = Depends(auth.verify_token)):
    """
    Manually triggers email dispatch for testing and returns the exact status message. (Guarded by Password JWT)
    """
    from .database import SessionLocal
    from . import models
    from .config import settings
    import pytz
    from datetime import datetime
    
    db = SessionLocal()
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
        
        # Call mailer (which now returns (success: bool, detail: str))
        from .mailer import send_daily_news_email
        success, message = send_daily_news_email(news_today, date_str)
        
        return {
            "success": success,
            "message": message,
            "news_count_sent": len(news_today),
            "smtp_configured": bool(settings.SMTP_USERNAME and settings.SMTP_PASSWORD),
            "smtp_username_val": settings.SMTP_USERNAME,
            "smtp_password_len": len(settings.SMTP_PASSWORD) if settings.SMTP_PASSWORD else 0
        }

    except Exception as e:
        return {
            "success": False,
            "error_type": str(type(e)),
            "error_message": str(e)
        }
    finally:
        db.close()


@app.get("/api/settings", response_model=schemas.SystemSettings)
def get_settings(db: Session = Depends(get_db), user: str = Depends(auth.verify_token)):
    """
    Get current system settings (recipient email list). (Guarded by Password JWT)
    """
    setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "email_recipient").first()
    
    if setting is None:
        recipients = []
        if settings.EMAIL_RECIPIENT:
            recipients = [settings.EMAIL_RECIPIENT.strip()]
        return {"email_recipients": recipients}
        
    recipients = []
    if setting.value:
        recipients = [e.strip() for e in setting.value.split(",") if e.strip()]
        
    return {"email_recipients": recipients}

@app.post("/api/settings", response_model=schemas.SystemSettings)
def update_settings(req: schemas.SystemSettings, db: Session = Depends(get_db), user: str = Depends(auth.verify_token)):
    """
    Update system settings (recipient email list). (Guarded by Password JWT)
    """
    cleaned_emails = []
    for email in req.email_recipients:
        clean = email.strip()
        if not clean:
            continue
        if "@" not in clean:
            raise HTTPException(status_code=400, detail=f"電子信箱「{clean}」格式不正確！")
        cleaned_emails.append(clean)
        
    joined_value = ",".join(cleaned_emails)
        
    setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "email_recipient").first()
    if not setting:
        setting = models.SystemSetting(key="email_recipient", value=joined_value)
        db.add(setting)
    else:
        setting.value = joined_value
        
    db.commit()
    return {"email_recipients": cleaned_emails}



@app.get("/api/keywords", response_model=List[schemas.Keyword])
def read_keywords(db: Session = Depends(get_db), user: str = Depends(auth.verify_token)):
    """
    List all active monitoring keywords. (Guarded by Password JWT)
    """
    return db.query(models.Keyword).order_by(models.Keyword.created_at.asc()).all()

@app.post("/api/keywords", response_model=schemas.Keyword)
def create_keyword(
    kw: schemas.KeywordCreate, 
    db: Session = Depends(get_db),
    user: str = Depends(auth.verify_token)
):
    """
    Add a new monitoring keyword and immediately run RSS bootstrap fetch. (Guarded by Password JWT)
    """
    clean_word = kw.word.strip()
    if not clean_word:
        raise HTTPException(status_code=400, detail="關鍵字不可為空值")
        
    db_kw = db.query(models.Keyword).filter(models.Keyword.word == clean_word).first()
    if db_kw:
        raise HTTPException(status_code=400, detail="此關鍵字已存在")
    
    new_kw = models.Keyword(word=clean_word)
    db.add(new_kw)
    db.commit()
    db.refresh(new_kw)
    
    # Bootstrap immediate fetch for the new keyword (both news and social posts)
    try:
        from .parser import fetch_social_posts
        news_items = fetch_google_news_rss(new_kw.word)
        social_items = fetch_social_posts(new_kw.word)
        all_items = news_items + social_items
        
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
        db.commit()
    except Exception as e:
        print(f"Error running bootstrap fetch for keyword '{new_kw.word}': {e}")
        db.rollback()
        
    return new_kw

@app.delete("/api/keywords/{kw_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_keyword(
    kw_id: int, 
    db: Session = Depends(get_db),
    user: str = Depends(auth.verify_token)
):
    """
    Delete a monitoring keyword by database ID. (Guarded by Password JWT)
    """
    db_kw = db.query(models.Keyword).filter(models.Keyword.id == kw_id).first()
    if not db_kw:
        raise HTTPException(status_code=404, detail="找不到此關鍵字")
    
    # Protect system default keywords from being deleted
    default_words = [
        "國立臺北教育大學",
        "國北教大",
        "北教大",
        "NTUE",
        "National Taipei University of Education"
    ]
    if db_kw.word in default_words:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此關鍵字為系統預設核心追蹤詞，無法刪除！"
        )
        
    db.delete(db_kw)
    db.commit()
    return None

@app.get("/api/scheduler/jobs", response_model=List[schemas.JobResponse])
def get_scheduler_jobs(user: str = Depends(auth.verify_token)):
    """
    List all active scheduled background tasks. (Guarded by Password JWT)
    """
    jobs = []
    for job in scheduler.scheduler.get_jobs():
        next_run = None
        if job.next_run_time:
            next_run = job.next_run_time.isoformat()
            
        jobs.append({
            "id": job.id,
            "name": job.name or job.id,
            "trigger": str(job.trigger),
            "next_run_time": next_run,
            "paused": job.next_run_time is None
        })
    return jobs

@app.post("/api/scheduler/jobs", response_model=schemas.JobResponse)
def create_scheduler_job(req: schemas.JobCreate, user: str = Depends(auth.verify_token)):
    """
    Register a new scheduled task (cron job) to fetch news. (Guarded by Password JWT)
    """
    if not (0 <= req.hour <= 23) or not (0 <= req.minute <= 59):
        raise HTTPException(status_code=400, detail="小時必須在 0-23 之間，分鐘必須在 0-59 之間")
        
    tz = pytz.timezone("Asia/Taipei")
    job_id = f"news_fetch_{req.hour}_{req.minute}"
    job_name = f"自動抓取新聞 {req.hour}:{str(req.minute).zfill(2)}"
    
    # Check if a job with this ID already exists
    existing_job = scheduler.scheduler.get_job(job_id)
    if existing_job:
        raise HTTPException(status_code=400, detail=f"已存在該時段 ({req.hour}:{str(req.minute).zfill(2)}) 的抓取任務！")
        
    try:
        job = scheduler.scheduler.add_job(
            scheduler.fetch_all_keywords_news,
            CronTrigger(hour=str(req.hour), minute=str(req.minute), timezone=tz),
            id=job_id,
            name=job_name,
            replace_existing=True
        )
        
        next_run = None
        if job.next_run_time:
            next_run = job.next_run_time.isoformat()
            
        return {
            "id": job.id,
            "name": job.name or job.id,
            "trigger": str(job.trigger),
            "next_run_time": next_run,
            "paused": False
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"註冊任務失敗: {str(e)}")

@app.post("/api/scheduler/jobs/{job_id}/run")
def trigger_scheduler_job(
    job_id: str, 
    background_tasks: BackgroundTasks,
    user: str = Depends(auth.verify_token)
):
    """
    Trigger a scheduled job to run immediately in a background task. (Guarded by Password JWT)
    """
    job = scheduler.scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="找不到此任務")
        
    background_tasks.add_task(job.func)
    return {"message": f"任務 '{job_id}' 已成功在背景觸發執行。"}

@app.post("/api/scheduler/jobs/{job_id}/toggle", response_model=schemas.JobResponse)
def toggle_scheduler_job(job_id: str, user: str = Depends(auth.verify_token)):
    """
    Pause or resume a scheduled job in real time. (Guarded by Password JWT)
    """
    job = scheduler.scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="找不到此任務")
        
    if job.next_run_time is None:
        job.resume()
        paused = False
    else:
        job.pause()
        paused = True
        
    next_run = None
    if job.next_run_time:
        next_run = job.next_run_time.isoformat()
        
    return {
        "id": job.id,
        "name": job.name or job.id,
        "trigger": str(job.trigger),
        "next_run_time": next_run,
        "paused": paused
    }

@app.delete("/api/scheduler/jobs/{job_id}")
def remove_scheduler_job(job_id: str, user: str = Depends(auth.verify_token)):
    """
    Delete a job from the scheduler memory. (Guarded by Password JWT)
    """
    job = scheduler.scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="找不到此任務")
        
    job.remove()
    return {"message": f"任務 '{job_id}' 已成功從排程記憶體中移除。"}

@app.post("/api/scheduler/jobs/reset")
def reset_scheduler_jobs(user: str = Depends(auth.verify_token)):
    """
    Reset scheduler tasks back to default settings. (Guarded by Password JWT)
    """
    # Remove existing cron jobs
    for job in scheduler.scheduler.get_jobs():
        scheduler.scheduler.remove_job(job.id)
            
    # Timezone Asia/Taipei
    tz = pytz.timezone("Asia/Taipei")

    # Re-register 7:30 - 10:00 and 16:00 - 18:00 triggers
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
        scheduler.scheduler.add_job(
            scheduler.fetch_all_keywords_news,
            CronTrigger(hour=h, minute=m, timezone=tz),
            id=job_id,
            name=job_name,
            replace_existing=True
        )
    
    return {"message": "系統已成功還原預設定時排程。"}

@app.get("/api/debug/install-playwright")
def debug_install_playwright():
    """
    Manually trigger Playwright Chromium installation and return console output.
    """
    import subprocess
    import sys
    try:
        print("[Playwright Trigger] Running manual install of Chromium...")
        res = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        return {
            "status": "success",
            "stdout": res.stdout,
            "stderr": res.stderr
        }
    except Exception as e:
        stdout_err = getattr(e, "stdout", "")
        stderr_err = getattr(e, "stderr", "")
        return {
            "status": "failed",
            "error": str(e),
            "stdout": stdout_err,
            "stderr": stderr_err
        }

@app.get("/api/debug/threads")
def debug_threads(keyword: str, db: Session = Depends(get_db)):
    """
    Debug endpoint to test Threads keyword collection and view metadata logs.
    """
    from .parser import collect_threads_posts
    trace, posts = collect_threads_posts(keyword)
    return trace

@app.get("/api/debug/social-time")
def debug_social_time(db: Session = Depends(get_db)):
    """
    Debug endpoint to check social post timestamps and filtering.
    """
    from datetime import datetime, timedelta
    
    now = datetime.utcnow()
    one_week_ago = now - timedelta(days=7)
    SOCIAL_SOURCES = ["Dcard", "PTT", "Threads", "Instagram"]
    
    posts = db.query(models.News).filter(
        models.News.source.in_(SOCIAL_SOURCES)
    ).order_by(
        func.coalesce(models.News.publish_time, models.News.crawled_at, models.News.created_at).desc()
    ).limit(20).all()
    
    results = []
    for p in posts:
        is_valid = True
        p_time = p.publish_time
        if p_time is None:
            is_valid = False
        else:
            if p_time.year <= 1971:
                is_valid = False
                
        display_time = p_time.isoformat() if (p_time and is_valid) else None
        
        crawled = p.crawled_at
        created = p.created_at
        
        included = False
        if crawled is not None:
            included = (crawled >= one_week_ago)
        else:
            if created is not None:
                included = (created >= one_week_ago)
                
        results.append({
            "id": p.id,
            "source": p.source,
            "title": p.title,
            "publish_time": p.publish_time.isoformat() if p.publish_time else None,
            "crawled_at": p.crawled_at.isoformat() if p.crawled_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "display_time": display_time,
            "is_publish_time_valid": is_valid,
            "included_by_recent_filter": included
        })
        
    return results
