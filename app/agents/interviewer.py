"""Роль 1. Интервьюер: задаёт следующий вопрос по плану."""
import re

from app import gigachat_client
from app.parsing import parse_key_values
from app.prompts import load_prompt
from app.schemas import InterviewPlan, Turn


def next_question(plan: InterviewPlan, history: list[Turn], topic_index: int,
                  clarify: bool = False) -> str:
    topic = (plan.topics[topic_index] if 0 <= topic_index < len(plan.topics)
             else "Профессиональный опыт")
    clarify = clarify and bool(history)
    context = (
        f"Роль: {plan.role}\nУровень: {plan.level}\nТемы интервью:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(plan.topics, 1))
        + f"\nТекущая тема: {topic}\nУточнение: {'да' if clarify else 'нет'}"
    )
    messages = [{"role": "user", "content": context}]
    for turn in history:
        messages.extend([
            {"role": "assistant", "content": turn.question},
            {"role": "user", "content": turn.answer},
        ])

    previous_questions = {turn.question.strip().casefold() for turn in history}
    if clarify:
        fallbacks = [
            f"Какой конкретный пример поясняет ваш последний ответ по теме «{topic}»?",
            f"Что именно вы сделали в описанной ситуации по теме «{topic}»?",
            f"Какой результат ваших действий подтверждает последний ответ по теме «{topic}»?",
        ]
    else:
        fallbacks = [
            f"Как вы применяли на практике навыки по теме «{topic}»?",
            f"С какой сложностью вы сталкивались при работе по теме «{topic}»?",
            f"Как вы проверяли результат работы по теме «{topic}»?",
        ]
    # shortcut: три запасных вопроса на тему; расширить при длинных диалогах без LLM.
    fallback = next((item for item in fallbacks if item.casefold() not in previous_questions),
                    f"Что ещё вы можете добавить по теме «{topic}»?")

    base_prompt, regular_prompt, clarification_prompt = load_prompt("interviewer").split("\n---\n")
    system_prompt = (base_prompt + "\n" + (clarification_prompt if clarify else regular_prompt)).format(
        topic=topic,
        last_answer=history[-1].answer if history else "нет ответа",
    )
    try:
        response = gigachat_client.chat(
            agent="interviewer",
            system_prompt=system_prompt,
            messages=messages,
            temperature=0.4,
        )
    except gigachat_client.LLMError:
        return fallback

    quotes = "\"'«»“”„*`"
    # Снимаем парное выделение, сохраняя оператор степени вроде 2 ** 3.
    text = re.sub(r"(?<!\w)\*\*(\S(?:.*?\S)?)\*\*(?!\w)", r"\1", response.strip())
    text = text.replace("`", "").strip(quotes).strip()
    values = parse_key_values(text, ["Вопрос"])
    if not values:
        # При пропущенном ключе принимаем и вопрос обычным текстом.
        values = parse_key_values(f"Вопрос: {text}", ["Вопрос"])
    question = values.get("Вопрос", "").strip().strip(quotes).strip()
    question, separator, _ = question.partition("?")
    if not separator or not question.strip():
        return fallback
    question = question.strip() + "?"
    if question.casefold() in previous_questions:
        return fallback
    return question
