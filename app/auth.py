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
    required = ("redirect_uri", "cookie_secret", "client_id",
                "client_secret", "server_metadata_url")
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


def clear_login_fields() -> None:
    st.session_state["_login_open"] = False
    for key in ("login_username", "login_password", "register_username", "register_password", "register_confirmation"):
        st.session_state.pop(key, None)


@st.dialog("Вход в аккаунт", on_dismiss=clear_login_fields)
def show_login() -> None:
    if st.session_state.get("session") is not None or st.session_state.get("pending") is not None:
        st.warning("После входа или регистрации текущее интервью начнётся заново. "
                   "Переход в Google также может сбросить интервью.")
    login_tab, register_tab = st.tabs(["Вход", "Регистрация"])
    with login_tab:
        with st.form("password_login", clear_on_submit=True):
            username = st.text_input(
                "Логин", max_chars=32, key="login_username")
            password = st.text_input(
                "Пароль", type="password", max_chars=128, key="login_password")
            submitted = st.form_submit_button("Войти", type="primary")
        if submitted:
            try:
                prepare_database()
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
                                     help="От 8 до 128 символов. Можно использовать длинную фразу.")
            confirmation = st.text_input(
                "Повторите пароль", type="password", max_chars=128, key="register_confirmation")
            submitted = st.form_submit_button(
                "Зарегистрироваться", type="primary")
        if submitted:
            if password != confirmation:
                st.error("Пароли не совпадают.")
            else:
                try:
                    prepare_database()
                    account = users.register(username, password)
                except (ValueError, users.StorageUnavailable) as error:
                    st.error(str(error))
                else:
                    _start_local_session(account)
    if auth_is_configured():
        st.button("Войти через Google", key="google_login", on_click=st.login)


def current_account() -> dict | None:
    """Возвращает проверенный аккаунт или гостя; гости не обращаются к БД.

    Ошибка проверки существующего аккаунта не превращает его в гостя неявно.
    """
    account = None
    subject = None
    st.session_state.pop("_auth_account", None)
    if auth_is_configured() and st.user.is_logged_in:
        google_sub = st.user.get("sub")
        if not google_sub:
            raise users.StorageUnavailable(
                "Не удалось определить аккаунт. Выйдите и войдите снова.")
        prepare_database()
        subject = f"google:{google_sub}"
        account = users.google_account(google_sub, st.user.get(
            "name") or "Аккаунт Google", st.user.get("email"))
    elif st.session_state.get("_auth_local_id"):
        if time.time() < st.session_state.get("_auth_expires", 0):
            prepare_database()
            account = users.local_account(st.session_state["_auth_local_id"])
            if account:
                subject = f"local:{account['id']}"
        if account is None:
            st.session_state.clear()

    if account is None:
        if st.session_state.get("_auth_subject"):
            st.session_state.clear()
        return None

    if st.session_state.get("_auth_subject") != subject:
        reset_interview()
        st.session_state["_auth_subject"] = subject
    st.session_state["_auth_account"] = account
    return account


def show_account_error(error: users.StorageUnavailable) -> None:
    st.error(str(error))
    if st.button("Повторить проверку"):
        st.rerun()
    st.button("Выйти в гостевой режим", on_click=logout)
    st.stop()
