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


def app(user=None, configured=True):
    test = AppTest.from_file(Path(__file__).resolve().parents[1] / "app/ui.py", default_timeout=30)
    test.secrets["auth"] = CONFIG if configured else {}
    auth.st.user.update(user or {"is_logged_in": False})
    return test


def test_missing_configuration_blocks_interview():
    test = app(configured=False).run()
    assert not test.exception
    assert test.info
    assert not test.text_area
    assert not test.button


def test_guest_cannot_access_interview_or_pending_action(monkeypatch):
    start = Mock()
    monkeypatch.setattr("app.orchestrator.InterviewSession.start", start)
    test = app()
    test.session_state["pending"] = ("start", "private vacancy")
    test.run()
    assert not test.exception
    assert [b.label for b in test.button] == ["Войти через Google"]
    assert not test.text_area
    start.assert_not_called()


def test_google_login_button_calls_streamlit(monkeypatch):
    login = Mock()
    monkeypatch.setattr(auth.st, "login", login)
    test = app().run()
    test.button[0].click().run()
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
    assert test.session_state["_auth_subject"] == "user-b"


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
    auth.logout()
    assert state == {}
    logout.assert_called_once_with()
