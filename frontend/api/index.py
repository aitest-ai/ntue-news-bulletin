import os
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, func, or_, and_
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
from typing import List, Optional
import httpx
import traceback
from datetime import datetime, timedelta, timezone
import pytz

# --- Database Setup ---
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Models ---
class Keyword(Base):
    __tablename__ = "keywords"
    id = Column(Integer, primary_key=True, index=True)
    word = Column(String(255), unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class News(Base):
    __tablename__ = "news"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(512), nullable=False)
    url = Column(Text, unique=True, index=True, nullable=False)
    source = Column(String(255), nullable=False)
    publish_time = Column(DateTime(timezone=True), nullable=True)
    keyword = Column(String(255), nullable=False)
    crawled_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class SystemSetting(Base):
    __tablename__ = "system_settings"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(255), unique=True, index=True, nullable=False)
    value = Column(Text, nullable=True)

class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"
    id = Column(String(255), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    hour = Column(Integer, nullable=False)
    minute = Column(Integer, nullable=False)
    paused = Column(Integer, default=0)

# --- Schemas ---
class LoginRequest(BaseModel):
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str

class NewsItem(BaseModel):
    id: int
    title: str
    url: str
    source: str
    publish_time: Optional[datetime]
    keyword: str
    crawled_at: Optional[datetime]
    created_at: Optional[datetime]

    class Config:
        orm_mode = True

class NewsResponse(BaseModel):
    total: int
    items: List[NewsItem]

class SystemSettingsSchema(BaseModel):
    email_recipients: List[str]

class KeywordSchema(BaseModel):
    id: int
    word: str
    created_at: Optional[datetime]

    class Config:
        orm_mode = True

class KeywordCreate(BaseModel):
    word: str

class JobResponse(BaseModel):
    id: str
    name: str
    trigger: str
    next_run_time: Optional[datetime]
    paused: bool

class JobCreate(BaseModel):
    hour: int
    minute: int

# --- Auth ---
import jwt
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
ALGORITHM = "HS256"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "ntue1234")

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=7)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("sub") != "admin":
            raise HTTPException(status_code=401, detail="Invalid token")
        return payload.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

# --- Dependencies ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- FastAPI App ---
app = FastAPI(title="Vercel Lightweight API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/auth/login", response_model=LoginResponse)
def login(req: LoginRequest):
    if req.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="密碼錯誤，拒絕存取系統！")
    token = create_access_token(data={"sub": "admin"})
    return {"access_token": token, "token_type": "bearer"}

@app.get("/api/news", response_model=NewsResponse)
def read_news(skip: int = 0, limit: int = 10, keyword: str = None, db: Session = Depends(get_db), user: str = Depends(verify_token)):
    try:
        query = db.query(News)
        if keyword:
            query = query.filter(News.keyword == keyword)
            
        now = datetime.now(timezone.utc)
        one_month_ago = now - timedelta(days=30)
        SOCIAL_SOURCES = ["Dcard", "PTT", "Threads", "Instagram"]
        
        is_social = News.source.in_(SOCIAL_SOURCES)
        is_news = ~News.source.in_(SOCIAL_SOURCES)
        
        social_valid_crawled = and_(News.crawled_at.isnot(None), News.crawled_at >= one_month_ago)
        social_valid_created = and_(News.crawled_at.is_(None), News.created_at >= one_month_ago)
        social_filter = and_(is_social, or_(social_valid_crawled, social_valid_created))
        
        query = query.filter(or_(is_news, social_filter))
        total = query.count()
        items = query.order_by(func.coalesce(News.publish_time, News.crawled_at, News.created_at).desc()).offset(skip).limit(limit).all()
        return {"total": total, "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/settings", response_model=SystemSettingsSchema)
def get_settings(db: Session = Depends(get_db), user: str = Depends(verify_token)):
    setting = db.query(SystemSetting).filter(SystemSetting.key == "email_recipient").first()
    if setting is None or not setting.value:
        email_rec = os.getenv("EMAIL_RECIPIENT", "").strip()
        return {"email_recipients": [email_rec] if email_rec else []}
    recipients = [e.strip() for e in setting.value.split(",") if e.strip()]
    return {"email_recipients": recipients}

@app.post("/api/settings", response_model=SystemSettingsSchema)
def update_settings(req: SystemSettingsSchema, db: Session = Depends(get_db), user: str = Depends(verify_token)):
    cleaned_emails = []
    for email in req.email_recipients:
        clean = email.strip()
        if clean and "@" in clean:
            cleaned_emails.append(clean)
    joined_value = ",".join(cleaned_emails)
    setting = db.query(SystemSetting).filter(SystemSetting.key == "email_recipient").first()
    if not setting:
        db.add(SystemSetting(key="email_recipient", value=joined_value))
    else:
        setting.value = joined_value
    db.commit()
    return {"email_recipients": cleaned_emails}

@app.get("/api/keywords", response_model=List[KeywordSchema])
def read_keywords(db: Session = Depends(get_db), user: str = Depends(verify_token)):
    return db.query(Keyword).order_by(Keyword.created_at.asc()).all()

@app.post("/api/keywords", response_model=KeywordSchema)
def create_keyword(kw: KeywordCreate, db: Session = Depends(get_db), user: str = Depends(verify_token)):
    clean_word = kw.word.strip()
    if db.query(Keyword).filter(Keyword.word == clean_word).first():
        raise HTTPException(status_code=400, detail="此關鍵字已存在")
    new_kw = Keyword(word=clean_word)
    db.add(new_kw)
    db.commit()
    db.refresh(new_kw)
    # Fire and forget to Render to bootstrap fetch
    try:
        RENDER_URL = os.getenv("RENDER_URL", "https://ntue-news-bulletin-backend.onrender.com")
        httpx.post(f"{RENDER_URL}/api/news/fetch", timeout=0.1)
    except httpx.TimeoutException:
        pass
    except Exception:
        pass
    return new_kw

@app.delete("/api/keywords/{keyword_id}")
def delete_keyword(keyword_id: int, db: Session = Depends(get_db), user: str = Depends(verify_token)):
    kw = db.query(Keyword).filter(Keyword.id == keyword_id).first()
    if not kw: raise HTTPException(status_code=404)
    db.query(News).filter(News.keyword == kw.word).delete()
    db.delete(kw)
    db.commit()
    return {"message": "已刪除"}

@app.post("/api/admin/wipe-all")
def wipe_all(db: Session = Depends(get_db), user: str = Depends(verify_token)):
    deleted = db.query(News).delete()
    db.commit()
    return {"message": f"Successfully wiped {deleted} old posts. Database is now clean!"}

@app.post("/api/news/fetch")
def trigger_fetch(user: str = Depends(verify_token)):
    """ Trigger GitHub Actions to run the scraper via repository_dispatch """
    try:
        token = os.getenv("GITHUB_PAT")
        repo = os.getenv("GITHUB_REPO", "aitest-ai/ntue-news-bulletin")
        if token:
            httpx.post(
                f"https://api.github.com/repos/{repo}/dispatches",
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "Authorization": f"token {token}"
                },
                json={"event_type": "trigger-fetch"},
                timeout=5.0
            )
            return {"message": "已成功通知 GitHub Actions 啟動背景抓取，請於 3 到 5 分鐘後重新整理網頁！", "new_articles_count": 0}
        else:
            return {"message": "系統尚未設定 GitHub Token (GITHUB_PAT)，目前只能依賴排程自動抓取。"}
    except Exception as e:
        print(f"Error triggering GitHub: {e}")
    return {"message": "已成功發送抓取指令，請稍候重整網頁。"}

@app.get("/api/scheduler/jobs", response_model=List[JobResponse])
def get_scheduler_jobs(db: Session = Depends(get_db), user: str = Depends(verify_token)):
    jobs = []
    for j in db.query(ScheduledJob).order_by(ScheduledJob.hour, ScheduledJob.minute).all():
        jobs.append({
            "id": j.id, "name": j.name, "trigger": f"cron[hour='{j.hour}', minute='{j.minute}']",
            "next_run_time": None, "paused": bool(j.paused)
        })
    return jobs

@app.post("/api/scheduler/jobs", response_model=JobResponse)
def create_scheduler_job(req: JobCreate, db: Session = Depends(get_db), user: str = Depends(verify_token)):
    job_id = f"news_fetch_{req.hour}_{req.minute}"
    new_job = ScheduledJob(id=job_id, name=f"自動抓取 {req.hour}:{req.minute}", hour=req.hour, minute=req.minute, paused=0)
    db.add(new_job)
    db.commit()
    return {"id": new_job.id, "name": new_job.name, "trigger": "", "next_run_time": None, "paused": False}

@app.post("/api/scheduler/jobs/{job_id}/toggle", response_model=JobResponse)
def toggle_scheduler_job(job_id: str, db: Session = Depends(get_db), user: str = Depends(verify_token)):
    job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
    job.paused = 0 if job.paused else 1
    db.commit()
    return {"id": job.id, "name": job.name, "trigger": "", "next_run_time": None, "paused": bool(job.paused)}

@app.delete("/api/scheduler/jobs/{job_id}")
def remove_scheduler_job(job_id: str, db: Session = Depends(get_db), user: str = Depends(verify_token)):
    db.query(ScheduledJob).filter(ScheduledJob.id == job_id).delete()
    db.commit()
    return {"message": "Deleted"}

@app.get("/api/scheduler/tick")
def tick_scheduler(db: Session = Depends(get_db)):
    """
    Called by Vercel Cron every 15 minutes to trigger due jobs.
    """
    try:
        jobs = db.query(ScheduledJob).filter(ScheduledJob.paused == 0).all()
        tz = pytz.timezone("Asia/Taipei")
        now = datetime.now(tz)
        now_mins = now.hour * 60 + now.minute
        
        triggered = False
        for job in jobs:
            job_mins = job.hour * 60 + job.minute
            diff = (now_mins - job_mins) % 1440
            
            # If the tick happens within 15 minutes after the scheduled time, trigger it
            if diff < 15:
                triggered = True
                break
                
        if triggered:
            token = os.getenv("GITHUB_PAT")
            repo = os.getenv("GITHUB_REPO", "aitest-ai/ntue-news-bulletin")
            if token:
                httpx.post(
                    f"https://api.github.com/repos/{repo}/dispatches",
                    headers={
                        "Accept": "application/vnd.github.v3+json",
                        "Authorization": f"token {token}"
                    },
                    json={"event_type": "trigger-fetch"},
                    timeout=5.0
                )
            return {"message": "Tick matched a job. Triggered GitHub Actions.", "triggered": True, "time": str(now)}
        
        return {"message": "No matching jobs. Tick skipped.", "triggered": False, "time": str(now)}
    except Exception as e:
        return {"message": f"Error: {e}", "triggered": False}

