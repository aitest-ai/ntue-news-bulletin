from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class LoginRequest(BaseModel):
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str

class KeywordBase(BaseModel):
    word: str

class KeywordCreate(KeywordBase):
    pass

class Keyword(KeywordBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

class NewsBase(BaseModel):
    title: str
    url: str
    source: str
    publish_time: datetime
    keyword: str

class News(NewsBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

class NewsResponse(BaseModel):
    total: int
    items: List[News]

class JobResponse(BaseModel):
    id: str
    name: str
    trigger: str
    next_run_time: Optional[str] = None
    paused: bool

class JobCreate(BaseModel):
    hour: int
    minute: int

class SystemSettings(BaseModel):
    email_recipients: List[str]



