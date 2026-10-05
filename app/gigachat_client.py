"""Клиент GigaChat: единственная точка вызова LLM, ею пользуются все агенты."""
import threading
import time

from gigachat import GigaChat

from app.config import settings
from app.llm_log import log_call


class LLMError(Exception):
    """Не удалось получить ответ от GigaChat после всех повторов."""


# Бесплатный тариф принимает один запрос за раз, поэтому вызовы идут по очереди.
_lock = threading.Lock()
_client: GigaChat | None = None


def _get_client() -> GigaChat:
    global _client
    if _client is None:
        _client = GigaChat(
            credentials=settings.credentials,
            scope=settings.scope,
            model=settings.model,
            verify_ssl_certs=settings.verify_ssl,
            timeout=settings.timeout_seconds,
        )
    return _client


def chat(agent: str, system_prompt: str, messages: list[dict], temperature: float = 0.7) -> str:
    """Отправляет промпт роли и историю сообщений, возвращает текст ответа модели.

    agent: имя агента для журнала, например "interviewer".
    messages: список вида [{"role": "user", "content": "..."}, {"role": "assistant", ...}].
    """
    payload = {
        "messages": [{"role": "system", "content": system_prompt}, *messages],
        "temperature": temperature,
    }
    last_error: Exception | None = None
    for attempt in range(settings.max_retries + 1):
        started = time.time()
        try:
            with _lock:
                response = _get_client().chat(payload)
            text = response.choices[0].message.content
            log_call(agent, system_prompt, messages, text, time.time() - started)
            return text
        except Exception as error:  # сеть, лимиты, сертификат: любая ошибка идёт на повтор
            last_error = error
            log_call(agent, system_prompt, messages, None, time.time() - started, str(error))
            time.sleep(2 ** attempt)
    raise LLMError(f"GigaChat не ответил после {settings.max_retries + 1} попыток: {last_error}")
