"""Opt-in integration tests; use an isolated temporary PostgreSQL schema."""
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from app import users

pytestmark = pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS") != "1", reason="Set RUN_POSTGRES_TESTS=1 with PostgreSQL running")
PASSWORD = "a sufficiently long password"


@pytest.fixture
def database(monkeypatch):
    original_connect = users.connect
    schema = "auth_test_" + uuid4().hex
    with original_connect() as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

    def connect():
        conn = original_connect()
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        return conn

    monkeypatch.setattr(users, "connect", connect)
    users.initialize_database()
    try:
        yield
    finally:
        with original_connect() as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_registration_login_and_persistence(database):
    user = users.register(" Alice ", PASSWORD)
    assert user["username"] == "alice"
    assert "password_hash" not in user
    assert users.authenticate("ALICE", PASSWORD)["id"] == user["id"]
    assert users.local_account(user["id"]) == user
    users.initialize_database()
    assert users.authenticate("alice", PASSWORD)["id"] == user["id"]
    with users.connect() as conn:
        row = conn.execute("SELECT password_hash FROM users").fetchone()
        assert row["password_hash"].startswith("$argon2id$")
        assert PASSWORD not in row["password_hash"]


def test_lockout_commits_and_expires(database):
    users.register("alice", PASSWORD)
    for _ in range(5):
        with pytest.raises(users.AccountError):
            users.authenticate("alice", "wrong")
    with pytest.raises(users.AccountError):
        users.authenticate("alice", PASSWORD)
    with users.connect() as conn:
        conn.execute("UPDATE users SET locked_until = now() - interval '1 second'")
    assert users.authenticate("alice", PASSWORD)["username"] == "alice"
    with users.connect() as conn:
        row = conn.execute("SELECT failed_attempts, locked_until FROM users").fetchone()
        assert row == {"failed_attempts": 0, "locked_until": None}


def test_concurrent_duplicate_registration(database):
    def register():
        try:
            return users.register("alice", PASSWORD)
        except users.AccountError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: register(), range(2)))
    assert sum(result is not None for result in results) == 1


def test_google_identity_is_stable_and_separate(database):
    local = users.register("alice", PASSWORD)
    google = users.google_account("google-sub", "Alice", "alice@example.com")
    again = users.google_account("google-sub", "New name", "new@example.com")
    assert google["id"] == again["id"]
    assert local["id"] != google["id"]
    assert users.local_account(google["id"]) is None
    assert again["email"] == "new@example.com"


def test_missing_and_wrong_password_have_same_error(database):
    users.register("alice", PASSWORD)
    messages = []
    for username in ("alice", "missing"):
        with pytest.raises(users.AccountError) as error:
            users.authenticate(username, "wrong")
        messages.append(str(error.value))
    assert messages[0] == messages[1]


def test_unavailable_database_hides_connection_details(monkeypatch):
    def fail():
        raise psycopg.OperationalError("secret connection details")
    monkeypatch.setattr(users, "connect", fail)
    with pytest.raises(users.StorageUnavailable) as error:
        users.initialize_database()
    assert "secret" not in str(error.value)
