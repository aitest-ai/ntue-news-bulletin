import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./ntue_bulletin.db")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "ntue1234")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "jwt_secret_key_ntue_bulletin_2026")
    JWT_ALGORITHM: str = "HS256"

    # SMTP Mailer Settings
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    EMAIL_RECIPIENT: str = os.getenv("EMAIL_RECIPIENT", "kancollect126@gmail.com")


    class Config:
        env_file = ".env"

settings = Settings()

