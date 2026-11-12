"""Вход через Google OIDC; проверку токенов выполняет Streamlit/Authlib."""
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


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
    st.session_state.clear()
    st.logout()


def require_login() -> None:
    """Не допускает к интервью без подтверждённой личности Google."""
    if not auth_is_configured():
        st.title("InterviewAI")
        st.info("Вход через Google пока недоступен. Попробуйте позже.")
        st.stop()

    if not st.user.is_logged_in:
        st.session_state.clear()
        st.title("Подготовьтесь к собеседованию")
        st.write("Войдите через Google, чтобы начать тренировочное интервью.")
        st.button("Войти через Google", on_click=st.login, type="primary")
        st.stop()

    subject = st.user.get("sub")
    if not subject:
        st.error("Не удалось определить аккаунт. Выйдите и войдите снова.")
        st.button("Выйти", on_click=logout)
        st.stop()

    # Не переносим ответы и отложенные действия между разными аккаунтами.
    if st.session_state.get("_auth_subject") != subject:
        st.session_state.clear()
        st.session_state["_auth_subject"] = subject


def show_account() -> None:
    with st.sidebar:
        st.text(st.user.get("name") or "Аккаунт Google")
        if st.user.get("email"):
            st.text(st.user["email"])
        st.button("Выйти", on_click=logout)
