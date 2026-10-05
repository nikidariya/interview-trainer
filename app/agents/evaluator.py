"""Роль 2. Оценщик: оценивает один ответ пользователя."""
from app.schemas import AnswerScore


def score_answer(question: str, answer: str) -> AnswerScore:
    # ЗАГЛУШКА: заменить на вызов gigachat_client.chat(...) и разбор через app.parsing
    return AnswerScore(scores={"Конкретика": 3, "Структура": 3}, comment="Заглушка", needs_followup=False)
