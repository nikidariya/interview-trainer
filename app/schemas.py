"""Общие структуры данных: через них части проекта передают друг другу информацию.

Правило: поля можно добавлять, существующие не менять и не удалять.
"""
from dataclasses import dataclass, field


@dataclass
class InterviewPlan:
    role: str
    level: str
    topics: list[str]


@dataclass
class Turn:
    question: str
    answer: str


@dataclass
class AnswerScore:
    scores: dict[str, int] = field(default_factory=dict)
    comment: str = ""
    needs_followup: bool = False
