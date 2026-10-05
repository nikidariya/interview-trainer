"""Роль 1. Аналитик вакансии: текст вакансии -> план интервью."""
from app.schemas import InterviewPlan


def build_plan(vacancy_text: str) -> InterviewPlan:
    # ЗАГЛУШКА: заменить на вызов gigachat_client.chat(...) и разбор через app.parsing
    return InterviewPlan(
        role="Роль из вакансии (заглушка)",
        level="junior",
        topics=["Тема 1 (заглушка)", "Тема 2 (заглушка)", "Тема 3 (заглушка)"],
    )
