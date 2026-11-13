import json

from app.orchestrator import InterviewSession
from app.schemas import InterviewPlan, AnswerScore, Turn


def test_session_roundtrip_and_continuation(monkeypatch):
    session = InterviewSession()
    session.plan = InterviewPlan("Python developer", "Junior", ["Python", "SQL"])
    session.history = [Turn("Первый вопрос", "Первый ответ")]
    session.scores = [AnswerScore({"Конкретика": 1}, "Подробнее", True)]
    session._current_question = "Уточнение"
    session._clarified = True
    restored = InterviewSession.from_dict(json.loads(json.dumps(session.to_dict())))
    assert restored.to_dict() == session.to_dict()
    monkeypatch.setattr("app.orchestrator.evaluator.score_answer", lambda *args: AnswerScore({"Конкретика": 1}))
    calls = []

    def question(plan, history, topic_index, **kwargs):
        calls.append((topic_index, kwargs))
        return "Вопрос SQL"

    monkeypatch.setattr("app.orchestrator.interviewer.next_question", question)
    assert restored.submit_answer("Уточнённый ответ") == "Вопрос SQL"
    assert calls == [(1, {})]  # Повторное уточнение той же темы не задаётся.
    assert restored.history[-1] == Turn("Уточнение", "Уточнённый ответ")
    assert len(restored.scores) == 2


def test_empty_session_roundtrip():
    session = InterviewSession()
    assert InterviewSession.from_dict(session.to_dict()).to_dict() == session.to_dict()
