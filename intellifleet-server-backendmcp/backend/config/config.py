from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    SECRET_KEY: Optional[str] = None
    EXPIRATION_TIME: Optional[int] = 3600
    GROQ_API_KEY: Optional[str] = None
    
    GOOGLE_MAPS_API_KEY: Optional[str] = None
    
    FRONTEND_URL: Optional[str] = None
    DEMO_ACCESS_ENABLED: bool = False
    BACKEND_URL: Optional[str] = None

    REDIS_URL: Optional[str] = None

    SMTP_SERVER: Optional[str] = None
    SMTP_PORT: Optional[int] = None
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAIL_FROM: str | None = None

    OPENAI_API_KEY: Optional[str] = None
    AI_PROVIDER: str = "openai"
    AZURE_AI_ENDPOINT: Optional[str] = None
    AZURE_AI_API_KEY: Optional[str] = None
    AZURE_AI_DEPLOYMENT: Optional[str] = None
    AZURE_AI_API_VERSION: str = "2024-10-21"
    AZURE_RESOURCE_GROUP: Optional[str] = None

    ALGORITHM: Optional[str] = None
    ACCESS_TOKEN_EXPIRE_MINUTES: Optional[int] = None
    TOKEN_EXPIRE_TIME_HOURS: Optional[int] = None
    
    DATABASE_URL: Optional[str] = None

    GEMINI_API_KEY: Optional[str] = None

settings = Settings()
