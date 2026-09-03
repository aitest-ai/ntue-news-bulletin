import os
import email.utils
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import httpx
import jwt
import pytz
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, String, Text, and_, create_engine, func, or_
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


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
        from_attributes = True


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
        from_attributes = True


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


SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
ALGORITHM = "HS256"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "ntue1234")
security = HTTPBearer()


def create_access_token(data: dict):
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(days=7)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("sub") != "admin":
            raise HTTPException(status_code=401, detail="Invalid token")
        return payload.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app = FastAPI(title="NTUE Opinion Monitor API", version="2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TAIPEI = pytz.timezone("Asia/Taipei")
SOCIAL_SOURCES = ["Dcard", "PTT", "Threads", "Instagram"]
DEFAULT_KEYWORDS = [
    "國立臺北教育大學",
    "國北教大",
    "北教大",
    "NTUE",
    "National Taipei University of Education",
]
DEFAULT_TIMES = [
    (7, 30), (8, 0), (8, 30), (9, 0), (9, 30), (10, 0),
    (16, 0), (16, 30), (17, 0), (17, 30), (18, 0),
]


def _now_taipei_naive():
    return datetime.now(TAIPEI).replace(tzinfo=None)


def _ensure_defaults(db: Session):
    if db.query(Keyword).count() == 0:
        for word in DEFAULT_KEYWORDS:
            db.add(Keyword(word=word))
    if db.query(ScheduledJob).count() == 0:
        for hour, minute in DEFAULT_TIMES:
            db.add(ScheduledJob(
                id=f"news_fetch_{hour}_{minute}",
                name=f"自動抓取新聞 {hour}:{minute:02d}",
                hour=hour,
                minute=minute,
                paused=0,
            ))
    db.commit()


def _keyword_query(words: List[str]):
    clean = [w.strip() for w in words if w and w.strip()]
    return "(" + " OR ".join(f'\"{w}\"' for w in clean[:12]) + ")"


def _match_keyword(title: str, keywords: List[str]):
    normalized = title.replace("臺", "台").lower()
    for keyword in keywords:
        if keyword.replace("臺", "台").lower() in normalized:
            return keyword
    return keywords[0] if keywords else "國北教大"


def _fetch_rss(task_name: str, query: str, keywords: List[str], forced_source: Optional[str], max_days: int):
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    headers = {"User-Agent": "Mozilla/5.0 NTUE-Opinion-Monitor/2.0"}
    response = httpx.get(url, headers=headers, timeout=8.0, follow_redirects=True)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    cutoff = _now_taipei_naive() - timedelta(days=max_days)
    items = []

    for node in root.findall(".//item")[:25]:
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        pub_raw = (node.findtext("pubDate") or "").strip()
        source_node = node.find("source")
        source = forced_source or (
            source_node.text.strip() if source_node is not None and source_node.text else "Google News"
        )
        if not title or not link or not pub_raw:
            continue
        try:
            dt = email.utils.parsedate_to_datetime(pub_raw)
            if dt.tzinfo:
                publish_time = dt.astimezone(TAIPEI).replace(tzinfo=None)
            else:
                publish_time = dt
        except Exception:
            continue
        if publish_time.year <= 1971 or publish_time < cutoff:
            continue
        clean_title = title
        if " - " in clean_title:
            clean_title = clean_title.rsplit(" - ", 1)[0].strip()
        items.append({
            "title": clean_title,
            "url": link,
            "source": source,
            "publish_time": publish_time,
            "keyword": _match_keyword(clean_title, keywords),
            "task": task_name,
        })

    return {"task": task_name, "status": "success", "count": len(items), "items": items}


def _collect_all(keywords: List[str]):
    base = _keyword_query(keywords)
    specs = [
        ("google_news", f"{base} when:14d", None, 30),
        ("dcard", f"{base} site:dcard.tw when:30d", "Dcard", 30),
        ("ptt", f"{base} site:ptt.cc when:30d", "PTT", 30),
        ("threads", f"{base} (site:threads.net OR site:threads.com) when:30d", "Threads", 30),
        ("instagram", f"{base} site:instagram.com when:30d", "Instagram", 30),
    ]
    results = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        future_map = {
            pool.submit(_fetch_rss, name, query, keywords, source, days): name
            for name, query, source, days in specs
        }
        for future in as_completed(future_map):
            name = future_map[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append({"task": name, "status": "failed", "count": 0, "items": [], "error": str(exc)[:300]})
    return sorted(results, key=lambda x: x["task"])


def _store_collection(db: Session, results):
    inserted = 0
    seen = set()
    for result in results:
        for item in result.get("items", []):
            url = item["url"]
            if url in seen:
                continue
            seen.add(url)
            if db.query(News).filter(News.url == url).first():
                continue
            db.add(News(
                title=item["title"],
                url=url,
                source=item["source"],
                publish_time=item["publish_time"],
                keyword=item["keyword"],
                crawled_at=datetime.utcnow(),
            ))
            inserted += 1
    db.commit()
    return inserted


def _run_collection(db: Session):
    _ensure_defaults(db)
    keywords = [k.word for k in db.query(Keyword).order_by(Keyword.id).all()]
    results = _collect_all(keywords)
    inserted = _store_collection(db, results)
    return {
        "status": "success" if any(r["status"] == "success" for r in results) else "failed",
        "inserted": inserted,
        "tasks": [{k: v for k, v in r.items() if k != "items"} for r in results],
        "finished_at": datetime.utcnow().isoformat(),
    }


def _schedule_due(db: Session):
    _ensure_defaults(db)
    now = datetime.now(TAIPEI)
    now_minutes = now.hour * 60 + now.minute
    jobs = db.query(ScheduledJob).filter(ScheduledJob.paused == 0).all()
    due = any((now_minutes - (job.hour * 60 + job.minute)) % 1440 < 15 for job in jobs)
    bucket = f"{now:%Y%m%d%H}-{now.minute // 15}"
    return due, bucket, now


def _get_setting(db: Session, key: str):
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    return row.value if row else None


def _set_setting(db: Session, key: str, value: str):
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(SystemSetting(key=key, value=value))
    db.commit()


@app.post("/api/auth/login", response_model=LoginResponse)
def login(req: LoginRequest):
    if req.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="密碼錯誤，拒絕存取系統！")
    return {"access_token": create_access_token({"sub": "admin"}), "token_type": "bearer"}


@app.get("/api/news", response_model=NewsResponse)
def read_news(skip: int = 0, limit: int = 100, keyword: str = None, db: Session = Depends(get_db), user: str = Depends(verify_token)):
    query = db.query(News)
    if keyword:
        query = query.filter(News.keyword == keyword)
    one_month_ago = datetime.now(timezone.utc) - timedelta(days=30)
    social = News.source.in_(SOCIAL_SOURCES)
    query = query.filter(or_(
        ~social,
        and_(social, or_(News.crawled_at >= one_month_ago, and_(News.crawled_at.is_(None), News.created_at >= one_month_ago)))
    ))
    total = query.count()
    items = query.order_by(func.coalesce(News.publish_time, News.crawled_at, News.created_at).desc()).offset(skip).limit(min(limit, 200)).all()
    return {"total": total, "items": items}


@app.get("/api/keywords", response_model=List[KeywordSchema])
def read_keywords(db: Session = Depends(get_db), user: str = Depends(verify_token)):
    _ensure_defaults(db)
    return db.query(Keyword).order_by(Keyword.created_at.asc()).all()


@app.post("/api/keywords", response_model=KeywordSchema)
def create_keyword(kw: KeywordCreate, db: Session = Depends(get_db), user: str = Depends(verify_token)):
    clean = kw.word.strip()
    if not clean:
        raise HTTPException(status_code=400, detail="關鍵字不可為空")
    if db.query(Keyword).filter(Keyword.word == clean).first():
        raise HTTPException(status_code=400, detail="此關鍵字已存在")
    row = Keyword(word=clean)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.delete("/api/keywords/{keyword_id}")
def delete_keyword(keyword_id: int, db: Session = Depends(get_db), user: str = Depends(verify_token)):
    row = db.query(Keyword).filter(Keyword.id == keyword_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="找不到關鍵字")
    db.delete(row)
    db.commit()
    return {"message": "已刪除"}


@app.post("/api/news/fetch")
def trigger_fetch(db: Session = Depends(get_db), user: str = Depends(verify_token)):
    result = _run_collection(db)
    return {"message": f"抓取完成，新增 {result['inserted']} 筆資料。", **result}


@app.post("/api/internal/scheduled-fetch")
def scheduled_fetch(db: Session = Depends(get_db)):
    due, bucket, now = _schedule_due(db)
    if not due:
        return {"triggered": False, "reason": "not_due", "time": now.isoformat()}
    if _get_setting(db, "last_schedule_bucket") == bucket:
        return {"triggered": False, "reason": "already_ran", "time": now.isoformat()}
    _set_setting(db, "last_schedule_bucket", bucket)
    result = _run_collection(db)
    return {"triggered": True, "time": now.isoformat(), **result}


@app.get("/api/status")
def system_status(db: Session = Depends(get_db), user: str = Depends(verify_token)):
    sources = {}
    for source in ["Google News", "Dcard", "PTT", "Threads", "Instagram"]:
        q = db.query(News).filter(News.source == source)
        latest = q.order_by(func.coalesce(News.crawled_at, News.created_at).desc()).first()
        sources[source] = {
            "count": q.count(),
            "last_seen": str(latest.crawled_at or latest.created_at) if latest else None,
        }
    return {"database": "ok", "sources": sources, "last_schedule_bucket": _get_setting(db, "last_schedule_bucket")}


@app.get("/api/settings", response_model=SystemSettingsSchema)
def get_settings(db: Session = Depends(get_db), user: str = Depends(verify_token)):
    value = _get_setting(db, "email_recipient") or os.getenv("EMAIL_RECIPIENT", "")
    return {"email_recipients": [x.strip() for x in value.split(",") if x.strip()]}


@app.post("/api/settings", response_model=SystemSettingsSchema)
def update_settings(req: SystemSettingsSchema, db: Session = Depends(get_db), user: str = Depends(verify_token)):
    cleaned = [x.strip() for x in req.email_recipients if x.strip() and "@" in x]
    _set_setting(db, "email_recipient", ",".join(cleaned))
    return {"email_recipients": cleaned}


@app.get("/api/scheduler/jobs", response_model=List[JobResponse])
def get_scheduler_jobs(db: Session = Depends(get_db), user: str = Depends(verify_token)):
    _ensure_defaults(db)
    return [{
        "id": j.id,
        "name": j.name,
        "trigger": f"Taipei {j.hour:02d}:{j.minute:02d}",
        "next_run_time": None,
        "paused": bool(j.paused),
    } for j in db.query(ScheduledJob).order_by(ScheduledJob.hour, ScheduledJob.minute).all()]


@app.post("/api/scheduler/jobs", response_model=JobResponse)
def create_scheduler_job(req: JobCreate, db: Session = Depends(get_db), user: str = Depends(verify_token)):
    if not (0 <= req.hour <= 23 and 0 <= req.minute <= 59):
        raise HTTPException(status_code=400, detail="時間格式不正確")
    job_id = f"news_fetch_{req.hour}_{req.minute}"
    if db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first():
        raise HTTPException(status_code=400, detail="此排程已存在")
    row = ScheduledJob(id=job_id, name=f"自動抓取 {req.hour}:{req.minute:02d}", hour=req.hour, minute=req.minute, paused=0)
    db.add(row)
    db.commit()
    return {"id": row.id, "name": row.name, "trigger": f"Taipei {row.hour:02d}:{row.minute:02d}", "next_run_time": None, "paused": False}


@app.post("/api/scheduler/jobs/{job_id}/toggle", response_model=JobResponse)
def toggle_scheduler_job(job_id: str, db: Session = Depends(get_db), user: str = Depends(verify_token)):
    row = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="找不到排程")
    row.paused = 0 if row.paused else 1
    db.commit()
    return {"id": row.id, "name": row.name, "trigger": f"Taipei {row.hour:02d}:{row.minute:02d}", "next_run_time": None, "paused": bool(row.paused)}


@app.delete("/api/scheduler/jobs/{job_id}")
def remove_scheduler_job(job_id: str, db: Session = Depends(get_db), user: str = Depends(verify_token)):
    row = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="找不到排程")
    db.delete(row)
    db.commit()
    return {"message": "Deleted"}


@app.post("/api/admin/wipe-all")
def wipe_all(db: Session = Depends(get_db), user: str = Depends(verify_token)):
    deleted = db.query(News).delete()
    db.commit()
    return {"message": f"已清除 {deleted} 筆資料"}
