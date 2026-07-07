from sqlalchemy import Column, Integer, String, Text, DateTime, func
from .database import Base

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
    publish_time = Column(DateTime(timezone=True), nullable=True)  # publishedAt (nullable)
    keyword = Column(String(255), nullable=False)
    crawled_at = Column(DateTime(timezone=True), server_default=func.now())  # crawledAt
    created_at = Column(DateTime(timezone=True), server_default=func.now())  # createdAt

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
    paused = Column(Integer, default=0) # 0 = active, 1 = paused

