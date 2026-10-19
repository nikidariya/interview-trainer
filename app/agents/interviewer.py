"""Роль 1. Интервьюер: задаёт следующий вопрос по плану."""
import re

from app import gigachat_client
from app.parsing import parse_key_values
from app.prompts import load_prompt
from app.schemas import InterviewPlan, Turn


_CONTEXT_TEMPLATE = (
    "Роль: {role}\nУровень: {level}\nТемы интервью:\n{topics}\n"
    "Текущая тема: {topic}\nУточнение: {clarify}"
)
_QUESTION_QUOTES = "\"'«»“”„*`"
_EMPTY_QUESTION_ERROR = "Интервьюер вернул пустой вопрос. Проверьте ответ в logs/llm_calls.jsonl."
_REPEATED_QUESTION_ERROR = "Интервьюер повторил ранее заданный вопрос. Проверьте ответ в logs/llm_calls.jsonl."


def _build_messages(plan: InterviewPlan, history: list[Turn], topic: str,
                    clarify: bool) -> list[dict]:
    context = _CONTEXT_TEMPLATE.format(
        role=plan.role,
        level=plan.level,
        topics="\n".join(f"{index}. {item}" for index, item in enumerate(plan.topics, 1)),
        topic=topic,
        clarify="да" if clarify else "нет",
    )
    messages = [{"role": "user", "content": context}]
    for turn in history:
        messages.extend([
            {"role": "assistant", "content": turn.question},
            {"role": "user", "content": turn.answer},
        ])
    return messages


def _build_system_prompt(topic: str, history: list[Turn], clarify: bool) -> str:
    base_prompt, regular_prompt, clarification_prompt = load_prompt("interviewer").split("\n---\n")
    return (base_prompt + "\n" + (clarification_prompt if clarify else regular_prompt)).format(
        topic=topic,
        last_answer=history[-1].answer if history else "нет ответа",
    )


def next_question(plan: InterviewPlan, history: list[Turn], topic_index: int,
                  clarify: bool = False) -> str:
    if not (0 <= topic_index < len(plan.topics)):
        raise ValueError(f"topic_index must be between 0 and {len(plan.topics)}")
    topic = plan.topics[topic_index]
    clarify = clarify and bool(history)
    messages = _build_messages(plan, history, topic, clarify)
    previous_questions = {turn.question.strip().casefold() for turn in history}
    system_prompt = _build_system_prompt(topic, history, clarify)
    response = gigachat_client.chat(
        agent="interviewer",
        system_prompt=system_prompt,
        messages=messages,
        temperature=0.4,
    )
    if not isinstance(response, str) or not response.strip():
        raise ValueError(_EMPTY_QUESTION_ERROR)

    # Снимаем парное выделение, сохраняя оператор степени вроде 2 ** 3.
    text = re.sub(r"(?<!\w)\*\*(\S(?:.*?\S)?)\*\*(?!\w)", r"\1", response.strip())
    text = text.replace("`", "").strip(_QUESTION_QUOTES).strip()
    lines = text.splitlines()
    values = {}
    for line in lines:
        values = parse_key_values(line, ["Вопрос"])
        if values:
            break
    first_line = lines[0] if lines else ""
    if not values and first_line.rstrip(":：- ").casefold() != "вопрос":
        # При пропущенном ключе принимаем и вопрос обычным текстом.
        values = parse_key_values(f"Вопрос: {first_line}", ["Вопрос"])
    question = values.get("Вопрос", "").strip().strip(_QUESTION_QUOTES).strip()
    question, separator, _ = question.partition("?")
    if not question.strip():
        raise ValueError(_EMPTY_QUESTION_ERROR)
    question = question.strip() + separator
    if question.casefold() in previous_questions:
        raise ValueError(_REPEATED_QUESTION_ERROR)
    return question
