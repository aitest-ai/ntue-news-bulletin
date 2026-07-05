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
    
    # Auto-fetch synchronously once if the news database is empty on startup.
    # This prevents the race condition where the frontend requests news before the async bootstrapper runs.
    db = SessionLocal()
    try:
        news_count = db.query(models.News).count()
        if news_count == 0:
            print("Database is empty on startup. Triggering synchronous initial fetch bootstrap...")
            scheduler.fetch_all_keywords_news()
    except Exception as e:
        print(f"Error running initial news fetch on startup: {e}")
    finally:
        db.close()
        
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
    allow_origins=["*"],
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
    query = db.query(models.News)
    if keyword:
        query = query.filter(models.News.keyword == keyword)
    
    total = query.count()
    items = query.order_by(models.News.publish_time.desc()).offset(skip).limit(limit).all()
    return {"total": total, "items": items}

@app.post("/api/news/fetch")
def trigger_fetch(user: str = Depends(auth.verify_token)):
    """
    Manually triggers RSS fetch of news for all active keywords. (Guarded by Password JWT)
    """
    new_count = scheduler.fetch_all_keywords_news()
    return {"message": "新聞重新抓取完成！", "new_articles_count": new_count}

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
            "recipient": settings.EMAIL_RECIPIENT
        }
    except Exception as e:
        return {
            "success": False,
            "error_type": str(type(e)),
            "error_message": str(e)
        }
    finally:
        db.close()


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
    
    # Bootstrap immediate fetch for the new keyword
    try:
        items = fetch_google_news_rss(new_kw.word)
        for item in items:
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
