"""Вход через Google OIDC или локальный аккаунт с паролем."""
import time

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from app import users

LOCAL_SESSION_SECONDS = 12 * 60 * 60


@st.cache_resource
def prepare_database() -> None:
    users.initialize_database()


def reset_interview() -> None:
    """Сбрасывает интервью, сохраняя аутентификацию и её срок действия."""
    for key in list(st.session_state):
        if not key.startswith("_auth_"):
            del st.session_state[key]


def auth_is_configured() -> bool:
    try:
        auth = st.secrets.get("auth", {})
    except StreamlitSecretNotFoundError:
        return False
    required = ("redirect_uri", "cookie_secret", "client_id", "client_secret", "server_metadata_url")
    return all(
        isinstance(auth.get(key), str)
        and auth[key].strip()
        and not auth[key].startswith("REPLACE_")
        for key in required
    )


def logout() -> None:
    google = auth_is_configured() and st.user.is_logged_in
    st.session_state.clear()
    if google:
        st.logout()
    else:
        st.rerun()


def _start_local_session(account: dict) -> None:
    st.session_state.clear()
    st.session_state["_auth_local_id"] = account["id"]
    st.session_state["_auth_expires"] = time.time() + LOCAL_SESSION_SECONDS
    st.rerun()


def show_login() -> None:
    st.title("Подготовьтесь к собеседованию")
    st.write("Войдите в аккаунт или зарегистрируйтесь, чтобы начать интервью.")
    login_tab, register_tab = st.tabs(["Вход", "Регистрация"])
    with login_tab:
        with st.form("password_login", clear_on_submit=True):
            username = st.text_input("Логин", max_chars=32, key="login_username")
            password = st.text_input("Пароль", type="password", max_chars=128, key="login_password")
            submitted = st.form_submit_button("Войти", type="primary")
        if submitted:
            try:
                account = users.authenticate(username, password)
            except (ValueError, users.StorageUnavailable) as error:
                st.error(str(error))
            else:
                _start_local_session(account)
    with register_tab:
        with st.form("password_register", clear_on_submit=True):
            username = st.text_input("Логин", max_chars=32, key="register_username",
                                     help="3–32 символа: латинские буквы, цифры, _, . или -; регистр не учитывается.")
            password = st.text_input("Пароль", type="password", max_chars=128, key="register_password",
                                     help="От 15 до 128 символов. Можно использовать длинную фразу.")
            confirmation = st.text_input("Повторите пароль", type="password", max_chars=128)
            submitted = st.form_submit_button("Зарегистрироваться", type="primary")
        if submitted:
            if password != confirmation:
                st.error("Пароли не совпадают.")
            else:
                try:
                    account = users.register(username, password)
                except (ValueError, users.StorageUnavailable) as error:
                    st.error(str(error))
                else:
                    _start_local_session(account)
    if auth_is_configured():
        st.divider()
        st.button("Войти через Google", on_click=st.login)


def require_login() -> None:
    """Проверяет личность до отрисовки интервью и выполнения действий LLM."""
    try:
        prepare_database()
    except users.StorageUnavailable as error:
        st.error(str(error))
        st.stop()

    account = None
    subject = None
    try:
        if auth_is_configured() and st.user.is_logged_in:
            google_sub = st.user.get("sub")
            if not google_sub:
                st.error("Не удалось определить аккаунт. Выйдите и войдите снова.")
                st.button("Выйти", on_click=logout)
                st.stop()
            subject = f"google:{google_sub}"
            account = users.google_account(google_sub, st.user.get("name") or "Аккаунт Google", st.user.get("email"))
        elif st.session_state.get("_auth_local_id"):
            if time.time() < st.session_state.get("_auth_expires", 0):
                account = users.local_account(st.session_state["_auth_local_id"])
                if account:
                    subject = f"local:{account['id']}"
            if account is None:
                st.session_state.clear()
    except users.StorageUnavailable as error:
        st.error(str(error))
        st.stop()

    if account is None:
        # Очищаем данные интервью, не стирая введённые значения форм.
        for key in ("session", "messages", "report", "pending", "error", "vacancy_draft", "vacancy_error",
                    "_auth_subject", "_auth_account"):
            st.session_state.pop(key, None)
        show_login()
        st.stop()

    if st.session_state.get("_auth_subject") != subject:
        reset_interview()
        st.session_state["_auth_subject"] = subject
    st.session_state["_auth_account"] = account


def show_account() -> None:
    with st.sidebar:
        account = st.session_state["_auth_account"]
        st.text(account["name"])
        if account.get("email"):
            st.text(account["email"])
        st.button("Выйти", on_click=logout)
