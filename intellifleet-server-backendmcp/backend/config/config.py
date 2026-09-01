from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    SECRET_KEY: Optional[str] = None
    EXPIRATION_TIME: Optional[int] = 3600
    GROQ_API_KEY: Optional[str] = None
    
    GOOGLE_MAPS_API_KEY: Optional[str] = None
    
    FRONTEND_URL: Optional[str] = None
    BACKEND_URL: Optional[str] = None

    REDIS_URL: Optional[str] = None

    SMTP_SERVER: Optional[str] = None
    SMTP_PORT: Optional[int] = None
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAIL_FROM: str | None = None

    OPENAI_API_KEY: Optional[str] = None

    ALGORITHM: Optional[str] = None
    ACCESS_TOKEN_EXPIRE_MINUTES: Optional[int] = None
    TOKEN_EXPIRE_TIME_HOURS: Optional[int] = None
    
    DATABASE_URL: Optional[str] = None

    GEMINI_API_KEY: Optional[str] = None

    class Config:
        env_file = ".env"
    
settings = Settings()
