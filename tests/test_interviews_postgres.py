import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest

from app import interviews, users
from app.orchestrator import InterviewSession
from app.schemas import InterviewPlan, Turn, AnswerScore
from test_users_postgres import database

pytestmark = pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS") != "1", reason="Requires PostgreSQL")


def create(user_id, **overrides):
    args = dict(user_id=user_id, interview_id=str(uuid4()), version=None,
                write_id=str(uuid4()), title="Python · Junior", vacancy="Python developer",
                status="preparing", snapshot={"schema_version": 1, "pending": ["start", "Python developer"]})
    args.update(overrides)
    return interviews.save_interview(**args), args


def test_persistence_order_and_idempotent_retry(database):
    user = users.register("alice", "long password")
    first, args = create(user["id"])
    second, _ = create(user["id"])
    assert [r["id"] for r in interviews.list_interviews(user["id"])] == [second["id"], first["id"]]
    retry = interviews.save_interview(**args)
    assert retry["version"] == 1
    assert retry["updated_at"] == first["updated_at"]
    args.update(version=1, write_id=str(uuid4()), status="completed", snapshot={"report": "Разбор"})
    saved = interviews.save_interview(**args)
    assert saved["version"] == 2
    assert interviews.save_interview(**args)["version"] == 2
    users.initialize_database()
    loaded = interviews.load_interview(user["id"], first["id"])
    assert loaded["snapshot"] == {"report": "Разбор"}
    assert loaded["status"] == "completed"
    assert interviews.list_interviews(user["id"])[0]["id"] == first["id"]


def test_ownership_for_reads_creates_and_updates(database):
    owner = users.register("alice", "long password")
    other = users.google_account("google-bob", "Bob", None)
    record, args = create(owner["id"])
    assert interviews.list_interviews(other["id"]) == []
    with pytest.raises(interviews.InterviewNotFound):
        interviews.load_interview(other["id"], record["id"])
    args["user_id"] = other["id"]
    for version in (None, 1):
        args["version"] = version
        with pytest.raises(interviews.InterviewNotFound):
            interviews.save_interview(**args)
    assert interviews.load_interview(owner["id"], record["id"])["version"] == 1


def test_full_snapshot_survives_database_roundtrip(database):
    user = users.google_account("google-alice", "Alice", None)
    session = InterviewSession()
    session.plan = InterviewPlan("Python", "Junior", ["Python", "SQL"])
    session.history = [Turn("Вопрос", "Ответ")]
    session.scores = [AnswerScore({"Конкретика": 2}, "Нужен пример", True)]
    session._current_question = "Уточнение"
    session._clarified = True
    snapshot = {"schema_version": 1, "session": session.to_dict(),
                "messages": [["assistant", "Вопрос"], ["user", "Ответ"], ["assistant", "Уточнение"]],
                "report": None, "pending": ["answer", "Новый ответ"], "error": None, "vacancy_error": None}
    record, _ = create(user["id"], snapshot=snapshot, status="in_progress")
    loaded = interviews.load_interview(user["id"], record["id"])
    assert loaded["snapshot"] == snapshot
    assert InterviewSession.from_dict(loaded["snapshot"]["session"]).to_dict() == session.to_dict()


def test_concurrent_updates_cannot_overwrite(database):
    user = users.register("alice", "long password")
    record, args = create(user["id"])

    def update(_):
        try:
            return interviews.save_interview(**{**args, "version": 1, "write_id": str(uuid4())})
        except interviews.InterviewConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, range(2)))
    assert sum(result is not None for result in results) == 1
    assert interviews.load_interview(user["id"], record["id"])["version"] == 2


def test_storage_errors_hide_connection_details(monkeypatch):
    def fail():
        raise psycopg.OperationalError("secret connection details")

    monkeypatch.setattr(users, "connect", fail)
    for operation in (lambda: interviews.list_interviews(str(uuid4())),
                      lambda: interviews.load_interview(str(uuid4()), str(uuid4())),
                      lambda: create(str(uuid4()))):
        with pytest.raises(users.StorageUnavailable) as error:
            operation()
        assert "secret" not in str(error.value)
