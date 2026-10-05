"""Журнал вызовов LLM: каждая строка файла logs/llm_calls.jsonl это один вызов агента."""
import json
import time
from pathlib import Path

from app.config import settings


def log_call(agent: str, system_prompt: str, messages: list[dict],
             response: str | None, seconds: float, error: str | None = None) -> None:
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "agent": agent,
        "system_prompt": system_prompt,
        "messages": messages,
        "response": response,
        "seconds": round(seconds, 2),
        "error": error,
    }
    with open(log_dir / "llm_calls.jsonl", "a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")
