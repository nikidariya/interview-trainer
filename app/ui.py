"""Роль 3. Интерфейс: чат с интервьюером на Streamlit."""
import streamlit as st

from app.orchestrator import InterviewSession

st.title("Тренажёр собеседований")

if "session" not in st.session_state:
    st.session_state.session = None
    st.session_state.messages = []
    st.session_state.report = None

if st.session_state.session is None:
    vacancy = st.text_area("Вставьте текст вакансии", height=250)
    if st.button("Начать интервью") and vacancy.strip():
        session = InterviewSession()
        first_question = session.start(vacancy)
        st.session_state.session = session
        st.session_state.messages = [("assistant", first_question)]
        st.rerun()
else:
    for role, text in st.session_state.messages:
        with st.chat_message(role):
            st.write(text)
    if st.session_state.report:
        st.subheader("Итоговый разбор")
        st.write(st.session_state.report)
    elif answer := st.chat_input("Ваш ответ"):
        st.session_state.messages.append(("user", answer))
        next_question = st.session_state.session.submit_answer(answer)
        if next_question is None:
            st.session_state.report = st.session_state.session.report()
        else:
            st.session_state.messages.append(("assistant", next_question))
        st.rerun()
