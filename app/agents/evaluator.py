"""Роль 2. Оценщик: оценивает один ответ пользователя."""
import re

from app.gigachat_client import LLMError, chat
from app.parsing import parse_key_values, parse_score
from app.prompts import load_prompt
from app.schemas import AnswerScore

CRITERIA = ["Конкретика", "Структура", "Релевантность", "Глубина"]
DEFAULT_SCORE = 3
FOLLOWUP_KEY = "Нужно уточнение"
COMMENT_KEY = "Комментарий"
FAILED_COMMENT = "Не удалось оценить ответ"


def _parse_followup(value: str | None, scores: dict[str, int]) -> bool:
    if value:
        word = value.strip().lower()
        if word.startswith("да"):
            return True
        if word.startswith("нет"):
            return False
    # Модель не ответила по формату: уточняем, если не хватает примеров или глубины.
    return min(scores["Конкретика"], scores["Глубина"]) <= 2


def score_answer(question: str, answer: str) -> AnswerScore:
    # Пустой ответ оцениваем без вызова модели: это экономит время ожидания.
    if len(re.sub(r"\W", "", answer or "")) < 3:
        return AnswerScore(scores={name: 1 for name in CRITERIA},
                           comment="Ответа почти нет.", needs_followup=True)

    message = f"Вопрос: {question.strip()}\n\nОтвет кандидата: {answer.strip()}"
    try:
        text = chat("evaluator", load_prompt("evaluator"),
                    [{"role": "user", "content": message}], temperature=0.1)
    except LLMError:
        return AnswerScore(scores={name: DEFAULT_SCORE for name in CRITERIA},
                           comment=FAILED_COMMENT, needs_followup=False)

    # GigaChat любит выделять ключи жирным (**Конкретика**: 4), а parser ждёт ключ в начале строки.
    values = parse_key_values(text.replace("*", ""), CRITERIA + [FOLLOWUP_KEY, COMMENT_KEY])
    scores = {name: parse_score(values.get(name), default=DEFAULT_SCORE) for name in CRITERIA}
    return AnswerScore(scores=scores,
                       comment=values.get(COMMENT_KEY, ""),
                       needs_followup=_parse_followup(values.get(FOLLOWUP_KEY), scores))
