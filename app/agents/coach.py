"""Роль 2. Тренер: итоговый разбор всего интервью."""
from app.schemas import AnswerScore, InterviewPlan, Turn


def final_report(plan: InterviewPlan, history: list[Turn], scores: list[AnswerScore]) -> str:
    # ЗАГЛУШКА: заменить на вызов gigachat_client.chat(...)
    return f"Итоговый разбор (заглушка): отвечено вопросов: {len(history)}."
