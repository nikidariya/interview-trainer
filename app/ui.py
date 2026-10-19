"""Роль 3. Интерфейс: чат с интервьюером на Streamlit"""
import streamlit as st

from app.gigachat_client import LLMError
from app.orchestrator import InterviewSession

MAX_VACANCY_CHARS = 6000


def init_state() -> None:
    """Создаёт переменные сессии при первом запуске страницы"""
    defaults = {
        "session": None, "messages": [], "report": None, "pending": None, "error": None,
        "vacancy_error": None, "vacancy_draft": "",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def show_vacancy_form() -> None:
    """Поле для вакансии с проверкой длины"""
    if st.session_state.vacancy_error:
        st.warning(
            "Не получилось составить план интервью по этому тексту. "
            "Проверьте, что это описание вакансии, и попробуйте ещё раз"
        )
    vacancy = st.text_area("Вставьте текст вакансии", value=st.session_state.vacancy_draft, height=250)
    if not st.button("Начать интервью"):
        return
    vacancy = vacancy.strip()
    if not vacancy:
        st.warning("Вставьте текст вакансии")
    elif len(vacancy) > MAX_VACANCY_CHARS:
        st.warning(f"Текст слишком длинный: {len(vacancy)} символов, максимум {MAX_VACANCY_CHARS}")
    else:
        st.session_state.vacancy_error = None
        st.session_state.vacancy_draft = vacancy
        st.session_state.pending = ("start", vacancy)
        st.rerun()


def show_chat() -> None:
    """Переписка, прогресс, поле ввода ответа и итоговый разбор"""
    state = st.session_state
    session = state.session
    if session is not None and state.report is None:
        total = len(session.plan.topics)
        st.caption(f"Вопрос {min(session.topic_index + 1, total)} из {total}")

    for role, text in state.messages:
        with st.chat_message(role):
            st.write(text)

    if state.report:
        st.subheader("Итоговый разбор")
        st.write(state.report)
    elif session is not None:
        # Пока агент работает, поле заблокировано: второй запрос отправить нельзя.
        if answer := st.chat_input("Ваш ответ", disabled=state.pending is not None):
            state.messages.append(("user", answer))
            state.pending = ("answer", answer)
            st.rerun()


def run_pending() -> None:
    """Выполняет отложенное действие (start, answer или report) и обновляет состояние"""
    state = st.session_state
    kind, payload = state.pending
    try:
        if kind == "start":
            with st.spinner("Разбираю вакансию и готовлю первый вопрос..."):
                session = InterviewSession()
                first_question = session.start(payload)
            state.session = session
            state.messages.append(("assistant", first_question))
            state.pending = None
        elif kind == "answer":
            with st.spinner("Оцениваю ответ и готовлю следующий вопрос..."):
                next_question = state.session.submit_answer(payload)
            if next_question is None:
                state.pending = ("report", None)
            else:
                state.messages.append(("assistant", next_question))
                state.pending = None
        else:
            with st.spinner("Готовлю итоговый разбор..."):
                state.report = state.session.report()
            state.pending = None
    except LLMError as error:
        state.error = str(error)  # pending не сбрасываем, чтобы можно было повторить
    except ValueError as error:
        if kind != "start":
            raise
        state.pending = None
        state.vacancy_error = str(error)
    st.rerun()


def show_error_with_retry() -> None:
    st.error("Не удалось получить ответ от GigaChat. Проверьте интернет и ключ, затем повторите")
    with st.expander("Подробности"):
        st.write(st.session_state.error)
    if st.button("Повторить"):
        st.session_state.error = None
        st.rerun()


st.title("Тренажёр собеседований")
init_state()

busy = st.session_state.pending is not None and not st.session_state.error
if st.sidebar.button("Начать заново", disabled=busy):
    st.session_state.clear()
    st.rerun()

if st.session_state.session is None and st.session_state.pending is None:
    show_vacancy_form()
else:
    show_chat()
    if st.session_state.pending is not None:
        if st.session_state.error:
            show_error_with_retry()
        else:
            run_pending()