from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from app import auth, interviews
from app.gigachat_client import LLMError
from app.schemas import AnswerScore, InterviewPlan
from test_auth import app, google_identity


@pytest.fixture
def history(monkeypatch, google_identity):
    records = {}

    def save(**args):
        previous = records.get(args["interview_id"])
        if previous and previous["last_write_id"] == args["write_id"]:
            return deepcopy(previous)
        if previous and previous["version"] != args["version"]:
            raise interviews.InterviewConflict("Изменено в другой вкладке")
        record = {**args, "id": args["interview_id"], "version": (args["version"] or 0) + 1,
                  "last_write_id": args["write_id"], "updated_at": datetime.now(timezone.utc)}
        records[record["id"]] = deepcopy(record)
        return deepcopy(record)

    def load(user_id, interview_id):
        record = records[interview_id]
        assert record["user_id"] == user_id
        return deepcopy(record)

    monkeypatch.setattr(interviews, "save_interview", save)
    monkeypatch.setattr(interviews, "load_interview", load)
    monkeypatch.setattr(interviews, "list_interviews", lambda user_id: sorted(
        [deepcopy(r) for r in records.values() if r["user_id"] == user_id],
        key=lambda r: r["updated_at"], reverse=True))
    monkeypatch.setattr("app.orchestrator.analyst.build_plan", Mock(return_value=InterviewPlan("Python", "Junior", ["Python", "SQL"])))
    monkeypatch.setattr("app.orchestrator.interviewer.next_question", Mock(return_value="Вопрос"))
    monkeypatch.setattr("app.orchestrator.evaluator.score_answer", Mock(return_value=AnswerScore({"Конкретика": 5})))
    monkeypatch.setattr("app.orchestrator.coach.final_report", Mock(return_value="Итоговый разбор"))
    return records


def signed_in():
    return app({"is_logged_in": True, "sub": "user-a", "name": "Alice"}).run()


def start(test):
    test.text_area[0].input("Python developer")
    next(b for b in test.button if "Начать интервью" in b.label).click().run()
    assert not test.exception
    return test.session_state["interview_id"]


def click(test, label):
    next(b for b in test.button if b.label == label).click().run()
    assert not test.exception


def test_history_resume_new_interview_and_report(history):
    test = signed_in()
    assert not history  # Пустая форма не создаёт интервью.
    first = start(test)
    test.chat_input[0].set_value("Первый ответ").run()
    assert history[first]["snapshot"]["session"]["topic_index"] == 1
    click(test, "Новое интервью")
    assert test.text_area[0].value == ""
    second = start(test)
    assert len(history) == 2
    assert second != first
    click(test, "Выйти")
    test = signed_in()
    assert test.text_area
    test.button(key=f"interview_{first}").click().run()
    assert test.session_state["session"].topic_index == 1
    assert len(test.chat_message) == 3
    test.chat_input[0].set_value("Второй ответ").run()
    assert not test.exception
    assert history[first]["status"] == "completed"
    test = signed_in()
    test.button(key=f"interview_{first}").click().run()
    assert test.session_state["report"] == "Итоговый разбор"
    assert not test.chat_input
    # В другом аккаунте чужая история не появляется.
    other = app({"is_logged_in": True, "sub": "user-b"}).run()
    assert not [b for b in other.sidebar.button if b.key.startswith("interview_")]


def test_local_account_history(history, monkeypatch):
    user = {"id": "local-a", "name": "alice", "username": "alice", "email": None}
    monkeypatch.setattr(auth.users, "local_account", lambda _: user)
    test = app(configured=False)
    test.session_state["_auth_local_id"] = user["id"]
    test.session_state["_auth_expires"] = auth.time.time() + 100
    test.run()
    interview_id = start(test)
    assert history[interview_id]["user_id"] == "local-a"
    click(test, "Новое интервью")
    test.button(key=f"interview_{interview_id}").click().run()
    assert test.chat_input
    assert not test.exception


def test_failed_result_save_retries_without_model_call(history, monkeypatch):
    test = signed_in()
    interview_id = start(test)
    original = interviews.save_interview
    failure = True

    def save(**args):
        if failure and args["snapshot"]["session"]["history"]:
            raise auth.users.StorageUnavailable("Нет соединения")
        return original(**args)

    monkeypatch.setattr(interviews, "save_interview", save)
    from app.orchestrator import evaluator
    test.chat_input[0].set_value("Ответ").run()
    assert not test.exception
    assert test.chat_input[0].disabled
    assert test.button(key="new_interview").disabled
    assert test.button(key=f"interview_{interview_id}").disabled
    assert history[interview_id]["snapshot"]["pending"] == ("answer", "Ответ")
    assert evaluator.score_answer.call_count == 1
    failure = False
    click(test, "Повторить сохранение")
    assert evaluator.score_answer.call_count == 1
    assert not test.chat_input[0].disabled
    assert history[interview_id]["snapshot"]["pending"] is None
    assert len(history[interview_id]["snapshot"]["session"]["history"]) == 1


def test_pending_restoration_requires_explicit_resume(history, monkeypatch):
    from app.orchestrator import evaluator
    evaluator.score_answer.side_effect = LLMError("Ошибка модели")
    test = signed_in()
    interview_id = start(test)
    test.chat_input[0].set_value("Ответ").run()
    assert evaluator.score_answer.call_count == 1
    test = signed_in()
    test.button(key=f"interview_{interview_id}").click().run()
    assert evaluator.score_answer.call_count == 1
    evaluator.score_answer.side_effect = None
    click(test, "Продолжить интервью")
    assert evaluator.score_answer.call_count == 2
    assert test.session_state["messages"].count(("user", "Ответ")) == 1


def test_failed_initial_save_prevents_generation(history, monkeypatch):
    from app.orchestrator import analyst
    test = signed_in()
    save = interviews.save_interview
    monkeypatch.setattr(interviews, "save_interview", Mock(side_effect=auth.users.StorageUnavailable("Нет соединения")))
    interview_id = start(test)
    analyst.build_plan.assert_not_called()
    assert not history
    monkeypatch.setattr(interviews, "save_interview", save)
    click(test, "Повторить сохранение")
    assert list(history) == [interview_id]
    analyst.build_plan.assert_called_once()


def test_conflict_requires_reloading_saved_version(history):
    from app.orchestrator import evaluator
    test = signed_in()
    interview_id = start(test)
    history[interview_id]["version"] += 1
    test.chat_input[0].set_value("Несохранённый ответ").run()
    evaluator.score_answer.assert_not_called()
    assert test.button(key="new_interview").disabled
    click(test, "Загрузить актуальную версию")
    assert test.session_state["messages"] == [("assistant", "Вопрос")]
    assert not test.chat_input[0].disabled


def test_history_read_failure_can_retry(history, monkeypatch):
    listing = interviews.list_interviews
    monkeypatch.setattr(interviews, "list_interviews", Mock(side_effect=auth.users.StorageUnavailable("Нет соединения")))
    test = signed_in()
    assert test.sidebar.error
    monkeypatch.setattr(interviews, "list_interviews", listing)
    click(test, "Повторить загрузку истории")
    assert not test.sidebar.error


def test_report_failure_resumes_after_relogin(history):
    from app.orchestrator import coach, evaluator
    test = signed_in()
    interview_id = start(test)
    test.chat_input[0].set_value("Ответ 1").run()
    coach.final_report.side_effect = LLMError("Ошибка разбора")
    test.chat_input[0].set_value("Ответ 2").run()
    assert history[interview_id]["status"] == "awaiting_report"
    assert evaluator.score_answer.call_count == 2
    test = signed_in()
    test.button(key=f"interview_{interview_id}").click().run()
    assert coach.final_report.call_count == 1
    coach.final_report.side_effect = None
    click(test, "Продолжить интервью")
    assert evaluator.score_answer.call_count == 2
    assert test.session_state["report"] == "Итоговый разбор"
    assert history[interview_id]["status"] == "completed"


def test_lost_commit_confirmation_does_not_duplicate_interview(history, monkeypatch):
    from app.orchestrator import analyst
    test = signed_in()
    original = interviews.save_interview
    failed = False

    def save(**args):
        nonlocal failed
        result = original(**args)
        if not failed:
            failed = True
            raise auth.users.StorageUnavailable("Потеряно подтверждение")
        return result

    monkeypatch.setattr(interviews, "save_interview", save)
    interview_id = start(test)
    assert len(history) == 1
    analyst.build_plan.assert_not_called()
    click(test, "Повторить сохранение")
    assert list(history) == [interview_id]
    assert history[interview_id]["version"] == 2
    analyst.build_plan.assert_called_once()


def test_invalid_vacancy_can_be_corrected_in_same_interview(history):
    from app.orchestrator import analyst
    analyst.build_plan.side_effect = ValueError("Не вакансия")
    test = signed_in()
    interview_id = start(test)
    assert test.warning
    assert history[interview_id]["snapshot"]["pending"] is None
    test = signed_in()
    test.button(key=f"interview_{interview_id}").click().run()
    assert test.text_area[0].value == "Python developer"
    analyst.build_plan.side_effect = None
    test.text_area[0].input("SQL developer")
    click(test, "Начать интервью →")
    assert len(history) == 1
    assert history[interview_id]["vacancy"] == "SQL developer"
    assert test.chat_input
