"""Роль 2. Тренер: итоговый разбор всего интервью."""
import re

from app.gigachat_client import LLMError, chat
from app.prompts import load_prompt
from app.schemas import AnswerScore, InterviewPlan, Turn

# Ограничения на размер сообщения: длинную историю сокращаем, чтобы уложиться в контекст модели.
MAX_ANSWER_CHARS = 1200
MAX_DIALOG_CHARS = 12000

# GigaChat, несмотря на запрет в промпте, дописывает «пример улучшенного ответа» с выдуманными
# цифрами и инструментами. Такой блок вырезаем до следующего заголовка «### ...».
_INVENTED_EXAMPLE = re.compile(
    r"^[ \t>*_]*(?:Пример улучшенн|Пример ответа|Улучшенн\w* (?:ответ|верси)|Как мог бы звучать).*?(?=^###|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL)


def _remove_invented_examples(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", _INVENTED_EXAMPLE.sub("", text)).strip()


def _shorten(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + " …(ответ сокращён)"


def _total(score: AnswerScore | None) -> int | None:
    if score is None or not score.scores:
        return None
    return sum(score.scores.values())


def _format_turn(number: int, turn: Turn, score: AnswerScore | None) -> str:
    lines = [f"Вопрос {number}: {turn.question.strip()}",
             f"Ответ {number}: {_shorten(turn.answer, MAX_ANSWER_CHARS) or '(пустой ответ)'}"]
    if score is not None and score.scores:
        marks = ", ".join(f"{name} {value}" for name, value in score.scores.items())
        lines.append(f"Оценки: {marks}")
        if score.comment:
            lines.append(f"Комментарий оценщика: {score.comment}")
    return "\n".join(lines)


def _format_dialog(history: list[Turn], scores: list[AnswerScore]) -> str:
    """Собирает диалог в текст. Если он слишком длинный, выкидывает ходы из середины."""
    blocks = [_format_turn(i + 1, turn, scores[i] if i < len(scores) else None)
              for i, turn in enumerate(history)]
    if sum(len(block) for block in blocks) <= MAX_DIALOG_CHARS:
        return "\n\n".join(blocks)
    head, tail = [], []
    size = 0
    left, right = 0, len(blocks) - 1
    # Берём ходы попеременно с начала и с конца, пока помещаются.
    while left <= right:
        block = blocks[left] if len(head) <= len(tail) else blocks[right]
        if size + len(block) > MAX_DIALOG_CHARS:
            break
        size += len(block)
        if len(head) <= len(tail):
            head.append(block)
            left += 1
        else:
            tail.insert(0, block)
            right -= 1
    skipped = len(blocks) - len(head) - len(tail)
    return "\n\n".join([*head, f"(…пропущено ходов из середины интервью: {skipped}…)", *tail])


def _best_and_worst(scores: list[AnswerScore], count: int) -> tuple[int, int] | None:
    """Номера (с 1) лучшего и худшего ответа по сумме баллов; None, если все суммы равны."""
    totals = [(_total(score), i + 1) for i, score in enumerate(scores[:count])]
    totals = [(total, number) for total, number in totals if total is not None]
    if not totals or len({total for total, _ in totals}) < 2:
        return None
    return max(totals)[1], min(totals)[1]


def _build_message(plan: InterviewPlan, history: list[Turn], scores: list[AnswerScore],
                   with_extremes: bool) -> str:
    topics = "\n".join(f"- {topic}" for topic in plan.topics)
    parts = [f"Должность: {plan.role}", f"Уровень: {plan.level}", f"Темы интервью:\n{topics}",
             f"Диалог:\n\n{_format_dialog(history, scores)}"]
    # Лучший и худший ответ нужны только для проверки модели в ноутбуке, пользователю их не показываем.
    extremes = _best_and_worst(scores, len(history)) if with_extremes else None
    if extremes:
        parts.append(f"По оценкам лучший ответ №{extremes[0]}, худший ответ №{extremes[1]}.")
    parts.append("Напиши итоговый разбор по инструкции.")
    return "\n\n".join(parts)


def _fallback_report(history: list[Turn], scores: list[AnswerScore]) -> str:
    """Короткий разбор без LLM на случай, если GigaChat не ответил."""
    lines = ["Подробный разбор сейчас получить не удалось: сервис модели не ответил. "
             "Ниже краткая сводка по оценкам.", f"Отвечено вопросов: {len(history)}."]
    rated = [score for score in scores if score.scores]
    if rated:
        criteria = rated[0].scores.keys()
        for name in criteria:
            values = [score.scores[name] for score in rated if name in score.scores]
            lines.append(f"{name}: в среднем {sum(values) / len(values):.1f} из 5.")
    return "\n".join(lines)


def final_report(plan: InterviewPlan, history: list[Turn], scores: list[AnswerScore],
                 system_prompt: str | None = None) -> str:
    """system_prompt передаёт ноутбук проверки: свой промпт с разделом «Лучший и худший ответ»."""
    if not history:
        return "Интервью не состоялось: не было ни одного ответа, разбирать пока нечего."
    message = _build_message(plan, history, scores, with_extremes=system_prompt is not None)
    try:
        text = chat("coach", system_prompt or load_prompt("coach"),
                    [{"role": "user", "content": message}], temperature=0.5)
        return _remove_invented_examples(text)
    except LLMError:
        return _fallback_report(history, scores)
