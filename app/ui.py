"""Роль 3. Интерфейс: чат с интервьюером на Streamlit"""
from pathlib import Path

import streamlit as st

from app.gigachat_client import LLMError
from app.orchestrator import InterviewSession

MAX_VACANCY_CHARS = 6000

# иконки в стиле Lucide (inline SVG, чтобы не зависеть от внешних файлов)
_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="{s}" height="{s}" viewBox="0 0 24 24" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{p}</svg>'
ICONS = {
    "brain": '<path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/><path d="M12 5v13"/>',
    "sparkles": '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 3v4M21 5h-4"/>',
    "briefcase": '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
    "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    "chat": '<path d="M14 9a2 2 0 0 1-2 2H6l-4 4V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2z"/><path d="M18 9h2a2 2 0 0 1 2 2v11l-4-4h-6a2 2 0 0 1-2-2v-1"/>',
    "chart": '<path d="M5 21v-6M12 21V9M19 21V3"/>',
}


def icon(name: str, size: int = 22, color: str = "#111111") -> str:
    return _SVG.format(s=size, c=color, p=ICONS[name])


def load_css() -> None:
    """Подключает app/style.css (лежит в app/, поэтому попадает и в Docker-образ)"""
    css = (Path(__file__).parent / "style.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def show_navbar(busy: bool) -> None:
    """Шапка: логотип слева, «Начать заново» справа (во время интервью)"""
    with st.container(key="navbar"):
        left, right = st.columns([4, 1], vertical_alignment="center")
    with left:
        st.markdown(
            f'<div class="brand-row"><div class="logo">{icon("brain", 24)}</div>'
            '<span class="brand">InterviewAI</span></div>',
            unsafe_allow_html=True,
        )
    with right:
        started = st.session_state.session is not None or st.session_state.pending is not None
        if started and st.button("↺ Начать заново", disabled=busy, use_container_width=True):
            st.session_state.clear()
            st.rerun()


# пиксельная звёздочка-«искра» для декора
SPARKLE = (
    '<svg width="34" height="34" viewBox="0 0 9 9" shape-rendering="crispEdges">'
    '<path fill="#FFD43B" stroke="#111" stroke-width="0.4" '
    'd="M4 0h1v3h1v1h3v1H6v1H5v3H4V6H3V5H0V4h3V3h1z"/></svg>'
)


def show_hero() -> None:
    st.markdown(
        f'<div class="hero"><span class="sparkle s1">{SPARKLE}</span><span class="sparkle s2">{SPARKLE}</span>'
        f'<span class="badge">{icon("sparkles", 16)} AI-интервью </span>'
        '<h1>Подготовься к реальному собеседованию</h1>'
        '<p>Вставь вакансию, пройди <mark>интервью</mark> и получи разбор ответов</p></div>',
        unsafe_allow_html=True,
    )


def show_features() -> None:
    items = [
        ("target", "По вакансии", "Вопросы под конкретные требования"),
        ("chat", "AI-интервью", "Вопросы по ходу диалога"),
        ("chart", "Разбор ответов", "Сильные и слабые стороны"),
    ]
    cards = "".join(
        f'<div class="feature">{icon(i, 30)}<b>{t}</b><span>{d}</span></div>' for i, t, d in items
    )
    st.markdown(f'<div class="features">{cards}</div>', unsafe_allow_html=True)


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
    show_hero()
    with st.container(key="card_vacancy"):
        st.markdown(f'<div class="card-title">{icon("briefcase")} Вакансия для собеседования</div>',
                    unsafe_allow_html=True)
        if st.session_state.vacancy_error:
            st.warning(
                "Не получилось составить план интервью по этому тексту. "
                "Проверьте, что это описание вакансии, и попробуйте ещё раз"
            )
        vacancy = st.text_area(
            "Текст вакансии", value=st.session_state.vacancy_draft, height=200,
            label_visibility="collapsed",
            placeholder="Вставьте сюда текст вакансии: описание компании, требования, обязанности и технологии…",
        )
        hint_col, button_col = st.columns([3, 1.3], vertical_alignment="center")
        with hint_col:
            st.markdown(f'<div class="hint">{icon("shield", 15, "#57534E")} '
                        f'Вопросы подбираются под вакансию',
                        unsafe_allow_html=True)
        with button_col:
            clicked = st.button("Начать интервью →", type="primary", use_container_width=True)
        message = None
        if clicked:
            vacancy = vacancy.strip()
            if not vacancy:
                message = "Вставьте текст вакансии"
            elif len(vacancy) > MAX_VACANCY_CHARS:
                message = f"Текст слишком длинный: {len(vacancy)} символов, максимум {MAX_VACANCY_CHARS}"
            else:
                st.session_state.vacancy_error = None
                st.session_state.vacancy_draft = vacancy
                st.session_state.pending = ("start", vacancy)
                st.rerun()
        if message:
            st.warning(message)
    show_features()


def show_chat() -> None:
    """Переписка, прогресс, поле ввода ответа и итоговый разбор"""
    state = st.session_state
    session = state.session
    if session is not None and state.report is None:
        total = len(session.plan.topics)
        current = min(session.topic_index + 1, total)
        st.progress(current / total, text=f"Вопрос {current} из {total}")

    for role, text in state.messages:
        with st.chat_message(role):
            st.markdown(text)

    if state.report:
        with st.container(key="card_report"):
            st.markdown(f'<div class="card-title">{icon("chart")} Итоговый разбор</div>',
                        unsafe_allow_html=True)
            st.markdown(state.report)
    elif session is not None:
        # пока агент работает, поле заблокировано, второй запрос отправить нельзя
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


st.set_page_config(page_title="InterviewAI — тренажёр собеседований", page_icon="🎯", layout="centered")
load_css()
init_state()

busy = st.session_state.pending is not None and not st.session_state.error
show_navbar(busy)

if st.session_state.session is None and st.session_state.pending is None:
    show_vacancy_form()
else:
    show_chat()
    if st.session_state.pending is not None:
        if st.session_state.error:
            show_error_with_retry()
        else:
            run_pending()