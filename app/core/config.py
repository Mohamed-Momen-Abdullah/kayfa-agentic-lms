import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Single source of truth for app configuration. Everything is read from
    the environment (or a local .env file) so nothing sensitive is hardcoded.
    """

    PROJECT_NAME: str = "Kayfa Learning Platform"

    # --- Database -----------------------------------------------------
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "kayfa_db")

    # --- Auth / JWT ------------------------------------------------------
    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-only-secret-change-me")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))

    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")

    # --- LLM (Groq) --------------------------------------------------------
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

    # --- External learning resources (optional) -------------------------
    YOUTUBE_API_KEY: str = os.getenv("YOUTUBE_API_KEY", "")

    # --- Observability (optional) ---------------------------------------
    LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    LANGFUSE_HOST: str = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
