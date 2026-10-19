"""Роль 1. Аналитик вакансии: текст вакансии -> план интервью."""
from app import gigachat_client
from app.parsing import parse_key_values, parse_numbered_list
from app.prompts import load_prompt
from app.schemas import InterviewPlan


def build_plan(vacancy_text: str) -> InterviewPlan:
    if not isinstance(vacancy_text, str) or not vacancy_text.strip():
        raise ValueError("Введите непустой текст вакансии.")
    vacancy = vacancy_text.strip()[:6000]
    response = gigachat_client.chat(
        agent="analyst",
        system_prompt=load_prompt("analyst"),
        messages=[{"role": "user", "content": vacancy}],
        temperature=0.2,
    )
    if not isinstance(response, str) or not response.strip():
        raise ValueError("Аналитик вакансии вернул пустой или некорректный ответ. Повторите попытку.")

    values = {}
    # Разбор по строкам не позволяет пустому полю захватить следующую строку.
    for line in response.splitlines():
        values.update(parse_key_values(line, ["Ошибка", "Роль", "Уровень"]))
    if "Ошибка" in values:
        raise ValueError(f"Не удалось составить план интервью: {values['Ошибка'].strip()}")
    role = values.get("Роль", "").strip()
    if not role:
        raise ValueError("В ответе аналитика отсутствует название профессии (Роль).")
    level = values.get("Уровень", "").strip().lower()
    if level not in {"junior", "middle", "senior"}:
        raise ValueError("В ответе аналитика должен быть указан уровень junior, middle или senior.")

    topics = [topic.strip() for topic in parse_numbered_list(response)]
    if len(topics) != 5 or not all(topics):
        raise ValueError("В ответе аналитика должно быть ровно 5 непустых тем интервью.")
    if len({topic.casefold() for topic in topics}) != 5:
        raise ValueError("Темы интервью в ответе аналитика должны быть разными.")

    return InterviewPlan(
        role=role,
        level=level,
        topics=topics,
    )
