"""Notification service configuration."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # SMTP Configuration
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "info@resonant.dev-swat.com"
    EMAIL_FROM_NAME: str = "DevSwat"
    
    # Database - use Docker service name in production
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/resonantgenesis"
    
    # Redis for pub/sub - use Docker service name in production
    REDIS_URL: str = "redis://redis:6379/0"
    
    # Templates
    TEMPLATE_DIR: str = "templates"
    
    class Config:
        env_prefix = ""
        extra = "ignore"


settings = Settings()
