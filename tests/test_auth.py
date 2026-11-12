from unittest.mock import Mock
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app import auth


CONFIG = {
    "redirect_uri": "http://localhost:8501/oauth2callback",
    "cookie_secret": "test-cookie-secret",
    "client_id": "test-client",
    "client_secret": "test-secret",
    "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
}


class User(dict):
    @property
    def is_logged_in(self):
        return self.get("is_logged_in", False)


@pytest.fixture(autouse=True)
def google_identity(monkeypatch):
    # AppTest doesn't run the real browser OIDC callback.
    monkeypatch.setattr(auth.st, "user", User())
    monkeypatch.setattr(auth, "prepare_database", Mock())
    monkeypatch.setattr(auth.users, "google_account", lambda subject, name, email: {
        "id": subject, "name": name, "email": email, "username": None,
    })


def app(user=None, configured=True):
    test = AppTest.from_file(Path(__file__).resolve().parents[1] / "app/ui.py", default_timeout=30)
    test.secrets["auth"] = CONFIG if configured else {}
    auth.st.user.update(user or {"is_logged_in": False})
    return test


def test_missing_google_configuration_still_allows_local_login():
    test = app(configured=False).run()
    assert not test.exception
    assert not test.text_area
    assert {b.label for b in test.button} == {"Войти", "Зарегистрироваться"}


def test_guest_cannot_access_interview_or_pending_action(monkeypatch):
    start = Mock()
    monkeypatch.setattr("app.orchestrator.InterviewSession.start", start)
    test = app()
    test.session_state["pending"] = ("start", "private vacancy")
    test.run()
    assert not test.exception
    assert "Войти через Google" in [b.label for b in test.button]
    assert not test.text_area
    start.assert_not_called()


def test_google_login_button_calls_streamlit(monkeypatch):
    login = Mock()
    monkeypatch.setattr(auth.st, "login", login)
    test = app().run()
    next(b for b in test.button if b.label == "Войти через Google").click().run()
    login.assert_called_once_with()


def test_signed_in_user_can_access_form_and_restart():
    test = app({"is_logged_in": True, "sub": "user-a", "name": "Alice"}).run()
    assert not test.exception
    assert test.text_area
    test.session_state["pending"] = ("start", "vacancy")
    test.session_state["error"] = "retry later"
    test.run()
    next(b for b in test.button if "Начать заново" in b.label).click().run()
    assert not test.exception
    assert test.text_area
    assert auth.st.user.is_logged_in


def test_account_switch_clears_previous_interview():
    test = app({"is_logged_in": True, "sub": "user-b"})
    test.session_state["_auth_subject"] = "user-a"
    test.session_state["messages"] = [("user", "private answer")]
    test.session_state["pending"] = ("start", "private vacancy")
    test.run()
    assert not test.exception
    assert test.session_state["messages"] == []
    assert test.session_state["pending"] is None
    assert test.session_state["_auth_subject"] == "google:user-b"


def test_missing_subject_blocks_interview():
    test = app({"is_logged_in": True}).run()
    assert not test.exception
    assert test.error
    assert not test.text_area


def test_logout_clears_session_before_delegating(monkeypatch):
    state = {"messages": ["private answer"], "_auth_subject": "user-a"}
    logout = Mock(side_effect=lambda: pytest.fail("session not cleared") if state else None)
    monkeypatch.setattr(auth.st, "session_state", state)
    monkeypatch.setattr(auth.st, "logout", logout)
    monkeypatch.setattr(auth, "auth_is_configured", lambda: True)
    auth.st.user["is_logged_in"] = True
    auth.logout()
    assert state == {}
    logout.assert_called_once_with()


LOCAL_USER = {"id": "local-id", "username": "alice", "name": "alice", "email": None}


def test_local_registration_and_logout(monkeypatch):
    register = Mock(return_value=LOCAL_USER)
    monkeypatch.setattr(auth.users, "register", register)
    monkeypatch.setattr(auth.users, "local_account", lambda user_id: LOCAL_USER)
    test = app(configured=False).run()
    test.text_input(key="register_username").input("alice")
    test.text_input(key="register_password").input("a long password phrase")
    next(x for x in test.text_input if x.label == "Повторите пароль").input("a long password phrase")
    next(b for b in test.button if b.label == "Зарегистрироваться").click().run()
    assert not test.exception
    register.assert_called_once_with("alice", "a long password phrase")
    assert test.text_area
    assert test.session_state["_auth_subject"] == "local:local-id"
    test.session_state["messages"] = [("user", "private")]
    next(b for b in test.button if b.label == "Выйти").click().run()
    assert not test.exception
    assert not test.text_area
    assert "_auth_local_id" not in test.session_state


def test_local_login_and_restart_preserve_session(monkeypatch):
    monkeypatch.setattr(auth.users, "authenticate", Mock(return_value=LOCAL_USER))
    monkeypatch.setattr(auth.users, "local_account", lambda user_id: LOCAL_USER)
    test = app(configured=False).run()
    test.text_input(key="login_username").input("alice")
    test.text_input(key="login_password").input("a long password phrase")
    next(b for b in test.button if b.label == "Войти").click().run()
    assert not test.exception
    expiry = test.session_state["_auth_expires"]
    test.session_state["pending"] = ("start", "vacancy")
    test.session_state["error"] = "retry later"
    test.run()
    next(b for b in test.button if "Начать заново" in b.label).click().run()
    assert not test.exception
    assert test.text_area
    assert test.session_state["_auth_expires"] == expiry


def test_expired_local_session_blocks_pending_work(monkeypatch):
    lookup = Mock()
    monkeypatch.setattr(auth.users, "local_account", lookup)
    test = app(configured=False)
    test.session_state["_auth_local_id"] = "local-id"
    test.session_state["_auth_expires"] = 0
    test.session_state["pending"] = ("start", "vacancy")
    test.run()
    assert not test.exception
    assert not test.text_area
    lookup.assert_not_called()


def test_password_confirmation_must_match(monkeypatch):
    register = Mock()
    monkeypatch.setattr(auth.users, "register", register)
    test = app(configured=False).run()
    test.text_input(key="register_username").input("alice")
    test.text_input(key="register_password").input("a long password phrase")
    next(b for b in test.button if b.label == "Зарегистрироваться").click().run()
    assert test.error[0].value == "Пароли не совпадают."
    register.assert_not_called()


def test_database_failure_blocks_interview(monkeypatch):
    monkeypatch.setattr(auth, "prepare_database", Mock(side_effect=auth.users.StorageUnavailable("Unavailable")))
    test = app({"is_logged_in": True, "sub": "user-a"}).run()
    assert not test.exception
    assert test.error
    assert not test.text_area
