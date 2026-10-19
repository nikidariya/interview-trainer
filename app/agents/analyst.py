"""Роль 1. Аналитик вакансии: текст вакансии -> план интервью."""
from app import gigachat_client
from app.parsing import parse_key_values, parse_numbered_list
from app.prompts import load_prompt
from app.schemas import InterviewPlan


_FALLBACK_TOPICS = (
    "Мотивация и интерес к выбранной профессии",
    "Опыт выполнения похожих рабочих задач",
    "Разбор сложной рабочей ситуации",
    "Взаимодействие с коллегами и заказчиками",
    "Проверка качества и результатов своей работы",
)


def build_plan(vacancy_text: str) -> InterviewPlan:
    vacancy = vacancy_text.strip()[:6000] if isinstance(vacancy_text, str) else ""
    response = ""
    if vacancy:
        try:
            response = gigachat_client.chat(
                agent="analyst",
                system_prompt=load_prompt("analyst"),
                messages=[{"role": "user", "content": vacancy}],
                temperature=0.2,
            )
        except gigachat_client.LLMError:
            # Клиент уже записал ошибку в журнал; интервью продолжится с общим планом.
            pass

    values = parse_key_values(response, ["Роль", "Уровень"])
    level = values.get("Уровень", "middle").strip().lower()
    if level not in {"junior", "middle", "senior"}:
        level = "middle"

    topics = []
    seen = set()
    for topic in [*parse_numbered_list(response), *_FALLBACK_TOPICS]:
        topic = topic.strip()
        if topic and topic.casefold() not in seen:
            topics.append(topic)
            seen.add(topic.casefold())
        if len(topics) == 5:
            break

    return InterviewPlan(
        role=values.get("Роль", "Специалист").strip() or "Специалист",
        level=level,
        topics=topics,
    )
