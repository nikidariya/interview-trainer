"""Настройки проекта: читаются из переменных окружения (файл .env)."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    credentials: str = os.getenv("GIGACHAT_CREDENTIALS", "")
    scope: str = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
    model: str = os.getenv("GIGACHAT_MODEL", "GigaChat")
    verify_ssl: bool = os.getenv("GIGACHAT_VERIFY_SSL", "true").lower() == "true"
    timeout_seconds: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "2"))
    log_dir: str = os.getenv("LOG_DIR", "logs")


settings = Settings()
