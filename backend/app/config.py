import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./ntue_bulletin.db")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "ntue1234")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "jwt_secret_key_ntue_bulletin_2026")
    JWT_ALGORITHM: str = "HS256"

    class Config:
        env_file = ".env"

settings = Settings()
