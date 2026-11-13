"""Хранилище интервью. Все операции ограничены владельцем аккаунта."""
import psycopg
from psycopg.types.json import Jsonb

from app import users


class InterviewConflict(RuntimeError):
    pass


class InterviewNotFound(RuntimeError):
    pass


def _record(row) -> dict:
    return {**row, "id": str(row["id"])}


def list_interviews(user_id: str) -> list[dict]:
    try:
        with users.connect() as conn:
            rows = conn.execute(
                """SELECT id, title, status, created_at, updated_at FROM interviews
                   WHERE user_id = %s ORDER BY updated_at DESC, id DESC""", (user_id,),
            ).fetchall()
            return [_record(row) for row in rows]
    except psycopg.Error:
        raise users.StorageUnavailable("Не удалось загрузить историю интервью. Попробуйте ещё раз.") from None


def load_interview(user_id: str, interview_id: str) -> dict:
    try:
        with users.connect() as conn:
            row = conn.execute(
                "SELECT * FROM interviews WHERE id = %s AND user_id = %s",
                (interview_id, user_id),
            ).fetchone()
            if row is None:
                raise InterviewNotFound("Интервью не найдено.")
            return _record(row)
    except psycopg.Error:
        raise users.StorageUnavailable("Не удалось открыть интервью. Попробуйте ещё раз.") from None


def save_interview(*, user_id: str, interview_id: str, version: int | None,
                   write_id: str, title: str, vacancy: str, status: str, snapshot: dict) -> dict:
    """Создать или атомарно сохранить снимок с проверкой версии.

    Стабильный write_id делает повтор записи безопасным даже при потере
    соединения после COMMIT. Повтор не меняет дату и не увеличивает версию.
    """
    try:
        with users.connect() as conn:
            if version is None:
                conn.execute(
                    """INSERT INTO interviews
                       (id, user_id, title, vacancy, status, last_write_id, snapshot)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (id) DO NOTHING""",
                    (interview_id, user_id, title, vacancy, status, write_id, Jsonb(snapshot)),
                )
            row = conn.execute(
                "SELECT * FROM interviews WHERE id = %s AND user_id = %s FOR UPDATE",
                (interview_id, user_id),
            ).fetchone()
            if row is None:
                raise InterviewNotFound("Интервью не найдено.")
            if str(row["last_write_id"]) == write_id:
                return _record(row)
            if row["version"] != version:
                raise InterviewConflict("Интервью изменилось в другой вкладке. Загрузите актуальную версию.")
            row = conn.execute(
                """UPDATE interviews SET title = %s, vacancy = %s, status = %s,
                   snapshot = %s, last_write_id = %s, version = version + 1, updated_at = now()
                   WHERE id = %s AND user_id = %s RETURNING *""",
                (title, vacancy, status, Jsonb(snapshot), write_id, interview_id, user_id),
            ).fetchone()
            return _record(row)
    except psycopg.Error:
        raise users.StorageUnavailable("Не удалось сохранить интервью. Повторите сохранение.") from None
