"""Роль 3. Интерфейс: чат с интервьюером на Streamlit"""
from pathlib import Path
from datetime import timedelta, timezone
from uuid import uuid4

import streamlit as st

from app import interviews
from app.auth import current_account, logout, reset_interview, show_account_error, show_login
from app.users import StorageUnavailable
from app.gigachat_client import LLMError
from app.link_reader import extract_url
from app.orchestrator import LINK_UNUSABLE_MESSAGE, InterviewSession

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


def show_navbar(busy: bool, account: dict | None) -> None:
    """Шапка: логотип слева, «Начать заново» справа (во время интервью)"""
    with st.container(key="navbar"):
        left, right = st.columns([3, 2], vertical_alignment="center")
    with left:
        st.markdown(
            f'<div class="brand-row"><div class="logo">{icon("brain", 24)}</div>'
            '<span class="brand">InterviewAI</span></div>',
            unsafe_allow_html=True,
        )
    with right:
        if account:
            st.text(account["name"])
            st.button("Выйти", on_click=logout, disabled=busy, use_container_width=True)
        elif st.button("Войти", key="open_login", disabled=busy, use_container_width=True):
            st.session_state["_login_open"] = True
        started = st.session_state.session is not None or st.session_state.pending is not None
        if not account and started and st.button("↺ Начать заново", disabled=busy, use_container_width=True):
            reset_interview()
            st.rerun()
    if not account and not busy and st.session_state.get("_login_open"):
        show_login()


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
        "interview_id": None, "interview_version": None, "write_id": None,
        "save_dirty": False, "save_error": None, "save_conflict": False,
        "resume_required": False,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def queue_save() -> None:
    if st.session_state.get("_auth_account"):
        state = st.session_state
        if state.interview_id is None:
            state.interview_id = str(uuid4())
        state.write_id = str(uuid4())
        state.save_dirty = True


def persist_interview() -> None:
    state = st.session_state
    if not state.save_dirty or state.save_error:
        return
    session = state.session
    snapshot = {
        "schema_version": 1,
        "session": session.to_dict() if session else None,
        "messages": state.messages,
        "report": state.report,
        "pending": state.pending,
        "error": state.error,
        "vacancy_error": state.vacancy_error,
    }
    status = ("completed" if state.report is not None else
              "awaiting_report" if state.pending and state.pending[0] == "report" else
              "in_progress" if session else "preparing")
    title = f"{session.plan.role} · {session.plan.level}" if session else "Новое интервью"
    try:
        record = interviews.save_interview(
            user_id=state._auth_account["id"], interview_id=state.interview_id,
            version=state.interview_version, write_id=state.write_id,
            title=title, vacancy=state.vacancy_draft, status=status, snapshot=snapshot,
        )
    except (StorageUnavailable, interviews.InterviewConflict, interviews.InterviewNotFound) as error:
        state.save_error = str(error)
        state.save_conflict = isinstance(error, (interviews.InterviewConflict, interviews.InterviewNotFound))
    else:
        state.interview_version = record["version"]
        state.save_dirty = False
        state.save_error = None
        state.save_conflict = False


def open_interview(interview_id: str) -> None:
    # Загрузку выполняем до сброса: ошибка чтения не уничтожает текущий диалог.
    record = interviews.load_interview(st.session_state._auth_account["id"], interview_id)
    snapshot = record["snapshot"]
    if snapshot.get("schema_version") != 1:
        raise StorageUnavailable("Эта версия интервью пока не поддерживается.")
    session = InterviewSession.from_dict(snapshot["session"]) if snapshot["session"] else None
    reset_interview()
    init_state()
    state = st.session_state
    state.interview_id = record["id"]
    state.interview_version = record["version"]
    state.vacancy_draft = record["vacancy"]
    state.session = session
    state.messages = [tuple(message) for message in snapshot["messages"]]
    state.report = snapshot["report"]
    state.pending = tuple(snapshot["pending"]) if snapshot["pending"] else None
    state.error = snapshot.get("error")
    state.vacancy_error = snapshot.get("vacancy_error")
    state.resume_required = state.pending is not None


def show_history(busy: bool) -> None:
    labels = {"preparing": "Подготовка", "in_progress": "В процессе",
              "awaiting_report": "Ожидает разбора", "completed": "Завершено"}
    with st.sidebar:
        st.header("История интервью")
        if st.button("Новое интервью", key="new_interview", disabled=busy, use_container_width=True):
            reset_interview()
            st.rerun()
        try:
            records = interviews.list_interviews(st.session_state._auth_account["id"])
            if not records:
                st.caption("Здесь появятся ваши интервью.")
            for record in records:
                date = record["updated_at"].astimezone(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M")
                if st.button(record["title"], key=f"interview_{record['id']}", disabled=busy,
                             type="primary" if record["id"] == st.session_state.interview_id else "secondary",
                             use_container_width=True):
                    open_interview(record["id"])
                    st.rerun()
                st.caption(f"{date} МСК · {labels[record['status']]}")
        except (StorageUnavailable, interviews.InterviewNotFound) as error:
            st.error(str(error))
            if st.button("Повторить загрузку истории"):
                st.rerun()


def show_save_error() -> None:
    state = st.session_state
    st.error(state.save_error)
    if state.save_conflict:
        st.caption("Загрузка актуальной версии заменит локальные несохранённые изменения.")
        if st.button("Загрузить актуальную версию"):
            try:
                open_interview(state.interview_id)
            except (StorageUnavailable, interviews.InterviewNotFound) as error:
                st.error(str(error))
            else:
                st.rerun()
    elif st.button("Повторить сохранение"):
        state.save_error = None
        st.rerun()


def show_vacancy_form() -> None:
    """Поле для вакансии с проверкой длины"""
    show_hero()
    with st.container(key="card_vacancy"):
        st.markdown(f'<div class="card-title">{icon("briefcase")} Вакансия для собеседования</div>',
                    unsafe_allow_html=True)
        if st.session_state.vacancy_error == LINK_UNUSABLE_MESSAGE:
            st.warning(LINK_UNUSABLE_MESSAGE)
        elif st.session_state.vacancy_error:
            st.warning(
                "Не получилось составить план интервью по этому тексту. "
                "Проверьте, что это описание вакансии, и попробуйте ещё раз"
            )
        vacancy = st.text_area(
            "Текст вакансии", value=st.session_state.vacancy_draft, height=200,
            key="vacancy_input", on_change=save_vacancy_draft,
            label_visibility="collapsed",
            placeholder="Вставьте сюда текст вакансии и/или ссылку на неё: описание компании, требования, обязанности и технологии…",
        )
        hint_col, button_col = st.columns([3, 1.3], vertical_alignment="center")
        with hint_col:
            st.markdown(f'<div class="hint">{icon("shield", 15, "#57534E")} '
                        f'Вопросы подбираются под вакансию. Можно прислать ссылку',
                        unsafe_allow_html=True)
        with button_col:
            clicked = st.button("Начать интервью →", type="primary", use_container_width=True)
        message = None
        if clicked:
            vacancy = vacancy.strip()
            if not vacancy:
                message = "Вставьте текст вакансии или ссылку на неё"
            elif len(vacancy) > MAX_VACANCY_CHARS:
                message = f"Текст слишком длинный: {len(vacancy)} символов, максимум {MAX_VACANCY_CHARS}"
            else:
                st.session_state.vacancy_error = None
                st.session_state.vacancy_draft = vacancy
                st.session_state.pending = ("start", vacancy)
                queue_save()
                st.rerun()
        if message:
            st.warning(message)
    show_features()


def save_vacancy_draft() -> None:
    st.session_state.vacancy_draft = st.session_state.vacancy_input


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
        if answer := st.chat_input("Ваш ответ", disabled=state.pending is not None or state.save_dirty):
            state.messages.append(("user", answer))
            state.pending = ("answer", answer)
            queue_save()
            st.rerun()


def run_pending() -> None:
    """Выполняет отложенное действие (start, answer или report) и обновляет состояние"""
    state = st.session_state
    kind, payload = state.pending
    try:
        if kind == "start":
            action = "Читаю ссылку и разбираю вакансию" if extract_url(payload) else "Разбираю вакансию"
            with st.spinner(f"{action} и готовлю первый вопрос..."):
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
            state.error = str(error)
        else:
            state.pending = None
            state.vacancy_error = str(error)
    queue_save()
    st.rerun()


def show_error_with_retry() -> None:
    st.error("Не удалось получить корректный ответ от GigaChat. Повторите чуть позже.")
    with st.expander("Подробности"):
        st.write(st.session_state.error)
    if st.button("Повторить"):
        st.session_state.error = None
        st.rerun()


st.set_page_config(page_title="InterviewAI — тренажёр собеседований", page_icon="🎯", layout="centered")
load_css()
try:
    account = current_account()
except StorageUnavailable as error:
    show_account_error(error)
init_state()
persist_interview()

busy = (st.session_state.save_dirty or
        (st.session_state.pending is not None and not st.session_state.error
         and not st.session_state.resume_required))
show_navbar(busy, account)
if account:
    show_history(busy)

if st.session_state.save_error:
    if st.session_state.session is not None:
        show_chat()
    show_save_error()
    st.stop()

if st.session_state.session is None and st.session_state.pending is None:
    show_vacancy_form()
else:
    show_chat()
    if st.session_state.pending is not None:
        if st.session_state.resume_required:
            st.info("В интервью осталось незавершённое действие.")
            if st.button("Продолжить интервью"):
                st.session_state.resume_required = False
                st.session_state.error = None
                st.rerun()
        elif st.session_state.error:
            show_error_with_retry()
        else:
            run_pending()
