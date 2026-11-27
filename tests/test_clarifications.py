import json
from unittest.mock import Mock

import pytest

from app.agents import interviewer
from app.gigachat_client import LLMError
from app.orchestrator import InterviewSession
from app.schemas import AnswerScore, Clarification, InterviewPlan, Turn


@pytest.fixture
def session(monkeypatch):
    value = InterviewSession()
    value.plan = InterviewPlan("Developer", "Junior", ["Python"])
    value._current_question = "Как вы использовали Python в проекте?"
    monkeypatch.setattr("app.orchestrator.evaluator.score_answer", Mock(return_value=AnswerScore({"Конкретика": 5})))
    monkeypatch.setattr(interviewer, "next_question", Mock(return_value="Какой конкретный пример вы можете привести?"))
    return value


@pytest.mark.parametrize("already_clarified", [False, True])
def test_clarifications_resume_and_answer_last_question(session, monkeypatch, already_clarified):
    from app.orchestrator import evaluator, coach

    session._clarified = already_clarified
    question = session._current_question
    chat = Mock(side_effect=[
        "Тип: уточнение\nСообщение: Расскажите о своём опыте в одном проекте.",
        "Тип: уточнение\nСообщение: Можно выбрать учебный проект.",
        "Тип: ответ",
    ])
    monkeypatch.setattr(interviewer.gigachat_client, "chat", chat)
    assert session.submit_answer("Поясните вопрос") == "Расскажите о своём опыте в одном проекте."
    restored = InterviewSession.from_dict(json.loads(json.dumps(session.to_dict())))
    assert restored.to_dict() == session.to_dict()
    assert restored.submit_answer("Учебный подойдёт?") == "Можно выбрать учебный проект."
    messages = chat.call_args.kwargs["messages"]
    assert messages == [
        {"role": "assistant", "content": question},
        {"role": "user", "content": "Поясните вопрос"},
        {"role": "assistant", "content": "Расскажите о своём опыте в одном проекте."},
        {"role": "user", "content": "Учебный подойдёт?"},
    ]
    assert restored._current_question == question
    assert restored.topic_index == 0
    assert restored._clarified is already_clarified
    assert restored.history == restored.scores == []
    evaluator.score_answer.assert_not_called()
    interviewer.next_question.assert_not_called()
    assert restored.submit_answer("Написал парсер на Python") is None
    evaluator.score_answer.assert_called_once_with(question, "Написал парсер на Python")
    assert restored.history == [Turn(question, "Написал парсер на Python")]
    assert len(restored.scores) == 1
    assert restored.clarifications == []
    report = Mock(return_value="Разбор")
    monkeypatch.setattr(coach, "final_report", report)
    assert restored.report() == "Разбор"
    report.assert_called_once_with(restored.plan, restored.history, restored.scores)


def test_explanation_does_not_consume_followup(session, monkeypatch):
    from app.orchestrator import evaluator

    monkeypatch.setattr(interviewer, "respond_to_message", Mock(side_effect=["Пояснение", None, "Ещё пояснение", None]))
    evaluator.score_answer.return_value = AnswerScore({"Конкретика": 1})
    session.submit_answer("Что имеется в виду?")
    assert session.submit_answer("Мало конкретики") == interviewer.next_question.return_value
    assert session._clarified is True
    assert session.clarifications == []
    interviewer.next_question.assert_called_once_with(session.plan, session.history, 0, clarify=True)
    session.submit_answer("Поясните дополнительный вопрос")
    assert session._clarified is True
    assert session.submit_answer("Всё ещё мало конкретики") is None
    assert len(session.scores) == 2


@pytest.mark.parametrize("failure_stage", ["routing", "evaluation", "next_question"])
def test_failure_preserves_context_and_retry(session, monkeypatch, failure_stage):
    from app.orchestrator import evaluator

    session.plan.topics.append("SQL")
    session.clarifications = [Clarification("Поясните", "Пояснение")]
    router = Mock(return_value=None)
    monkeypatch.setattr(interviewer, "respond_to_message", router)
    failing = {"routing": router, "evaluation": evaluator.score_answer,
               "next_question": interviewer.next_question}[failure_stage]
    failing.side_effect = LLMError("Недоступно")
    before = session.to_dict()
    with pytest.raises(LLMError):
        session.submit_answer("Мой ответ")
    assert session.to_dict() == before
    failing.side_effect = None
    session.submit_answer("Мой ответ")
    assert len(session.history) == len(session.scores) == 1
    assert session.clarifications == []


@pytest.mark.parametrize("response", [None, "", "Не по формату", "Тип: неизвестно", "Тип: уточнение", "Тип: уточнение\nСообщение:   "])
def test_invalid_routing_never_scores(session, monkeypatch, response):
    from app.orchestrator import evaluator

    monkeypatch.setattr(interviewer.gigachat_client, "chat", Mock(return_value=response))
    assert session.submit_answer("Поясните") == interviewer._INTENT_FALLBACK
    evaluator.score_answer.assert_not_called()
    assert session.topic_index == 0
    assert session.history == session.scores == []


def test_bold_routing_format(monkeypatch):
    monkeypatch.setattr(interviewer.gigachat_client, "chat", Mock(return_value="**Тип**: уточнение\n**Сообщение**: Пояснение."))
    assert interviewer.respond_to_message("Вопрос?", "Поясните", []) == "Пояснение."


def test_old_snapshot(session):
    snapshot = session.to_dict()
    del snapshot["clarifications"]
    restored = InterviewSession.from_dict(snapshot)
    assert restored.clarifications == []
    assert restored._current_question == session._current_question
