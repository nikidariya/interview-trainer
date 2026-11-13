"""Постоянные учётные записи в PostgreSQL. Пароли и секреты не логируются."""
import os
import secrets
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from app.config import settings  # загружает .env до чтения параметров БД
from app.passwords import hash_password, hasher, normalize_username, verify_password


class AccountError(ValueError):
    pass


class StorageUnavailable(RuntimeError):
    pass


_dummy_hash = hasher.hash(secrets.token_urlsafe(32))


def connect():
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=os.getenv("POSTGRES_PORT", "5433"),
        dbname=os.getenv("POSTGRES_DB", "interview_trainer"),
        user=os.getenv("POSTGRES_USER", "interview"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        connect_timeout=5,
        row_factory=dict_row,
    )


def initialize_database() -> None:
    """Идемпотентная начальная схема; блокировка защищает параллельный запуск."""
    try:
        with connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(82465101)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id UUID PRIMARY KEY,
                    username TEXT UNIQUE,
                    password_hash TEXT,
                    google_sub TEXT UNIQUE,
                    name TEXT NOT NULL,
                    email TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    last_login_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    failed_attempts INTEGER NOT NULL DEFAULT 0,
                    locked_until TIMESTAMPTZ,
                    CHECK ((username IS NOT NULL AND password_hash IS NOT NULL AND google_sub IS NULL)
                        OR (username IS NULL AND password_hash IS NULL AND google_sub IS NOT NULL))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS interviews (
                    id UUID PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES users(id),
                    title TEXT NOT NULL,
                    vacancy TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN
                        ('preparing', 'in_progress', 'awaiting_report', 'completed')),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    version INTEGER NOT NULL DEFAULT 1,
                    last_write_id UUID NOT NULL,
                    snapshot JSONB NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS interviews_user_updated_idx
                ON interviews (user_id, updated_at DESC, id DESC)
            """)
    except psycopg.Error:
        raise StorageUnavailable("Хранилище аккаунтов временно недоступно. Попробуйте позже.") from None


def _public(row) -> dict:
    return {key: str(row[key]) if key == "id" else row[key]
            for key in ("id", "username", "name", "email")}


def register(username: str, password: str) -> dict:
    username = normalize_username(username)
    password_hash = hash_password(password)
    try:
        with connect() as conn:
            row = conn.execute(
                """INSERT INTO users (id, username, password_hash, name)
                   VALUES (%s, %s, %s, %s) RETURNING *""",
                (uuid4(), username, password_hash, username),
            ).fetchone()
            return _public(row)
    except psycopg.errors.UniqueViolation:
        raise AccountError("Этот логин уже занят.") from None
    except psycopg.Error:
        raise StorageUnavailable("Не удалось создать аккаунт. Попробуйте позже.") from None


def authenticate(username: str, password: str) -> dict:
    message = "Неверный логин или пароль, либо вход временно ограничен. Попробуйте позже."
    try:
        username = normalize_username(username)
    except ValueError:
        raise AccountError(message) from None
    result = None
    try:
        with connect() as conn:
            row = conn.execute(
                "SELECT *, locked_until > now() AS locked FROM users WHERE username = %s FOR UPDATE",
                (username,),
            ).fetchone()
            if row is None:
                verify_password(_dummy_hash, password)
            elif not row["locked"]:
                if verify_password(row["password_hash"], password):
                    updated_hash = (hash_password(password) if hasher.check_needs_rehash(row["password_hash"])
                                    else row["password_hash"])
                    conn.execute(
                        """UPDATE users SET failed_attempts = 0, locked_until = NULL,
                           last_login_at = now(), password_hash = %s WHERE id = %s""",
                        (updated_hash, row["id"]),
                    )
                    result = _public(row)
                else:
                    # После истечения блокировки начинаем новый цикл попыток.
                    count = 1 if row["locked_until"] else row["failed_attempts"] + 1
                    conn.execute(
                        """UPDATE users SET failed_attempts = %s,
                           locked_until = CASE WHEN %s >= 5 THEN now() + interval '15 minutes'
                                              ELSE NULL END WHERE id = %s""",
                        (count, count, row["id"]),
                    )
    except psycopg.Error:
        raise StorageUnavailable("Вход временно недоступен. Попробуйте позже.") from None
    # Ошибка вне транзакции: счётчик неверных попыток должен сохраниться.
    if result is None:
        raise AccountError(message)
    return result


def google_account(subject: str, name: str, email: str | None) -> dict:
    try:
        with connect() as conn:
            row = conn.execute(
                """INSERT INTO users (id, google_sub, name, email) VALUES (%s, %s, %s, %s)
                   ON CONFLICT (google_sub) DO UPDATE
                   SET name = EXCLUDED.name, email = EXCLUDED.email, last_login_at = now()
                   RETURNING *""", (uuid4(), subject, name, email),
            ).fetchone()
            return _public(row)
    except psycopg.Error:
        raise StorageUnavailable("Вход временно недоступен. Попробуйте позже.") from None


def local_account(user_id: str) -> dict | None:
    try:
        with connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = %s AND username IS NOT NULL", (user_id,)).fetchone()
            return _public(row) if row else None
    except psycopg.Error:
        raise StorageUnavailable("Хранилище аккаунтов временно недоступно. Попробуйте позже.") from None
