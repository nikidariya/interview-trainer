"""Роль 1. Интервьюер: задаёт следующий вопрос по плану."""
from app.schemas import InterviewPlan, Turn


def next_question(plan: InterviewPlan, history: list[Turn], topic_index: int,
                  clarify: bool = False) -> str:
    # ЗАГЛУШКА: заменить на вызов gigachat_client.chat(...)
    # clarify=True означает, что нужно задать уточняющий вопрос по предыдущему ответу.
    return f"Вопрос по теме «{plan.topics[topic_index]}» (заглушка)"
