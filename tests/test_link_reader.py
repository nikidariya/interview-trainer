import httpx
import pytest

from app import link_reader, orchestrator
from app.agents import analyst
from app.orchestrator import LINK_UNUSABLE_MESSAGE, InterviewSession
from app.schemas import InterviewPlan

URL = "https://example.com/job"
PAGE = "Описание вакансии со страницы"


def test_extract_url_absent():
    assert link_reader.extract_url("Просто текст вакансии, www без схемы") is None


def test_extract_url_inside_text_without_punctuation():
    assert link_reader.extract_url(f"Вакансия ({URL}?a=1). Прошу учесть") == f"{URL}?a=1"


@pytest.mark.parametrize("url", [
    "http://localhost:8501/",
    "http://127.0.0.1/",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.1/",
    "http://[::1]/",
    "file:///etc/passwd",
])
def test_unsafe_urls_are_blocked(url):
    assert link_reader.is_safe_url(url) is False
    assert link_reader.fetch_page_text(url) is None


def _serve(monkeypatch, handler):
    """Подменяет сеть: httpx получает ответы от handler, все адреса кроме private.test считаются безопасными."""
    real_client = httpx.Client
    monkeypatch.setattr(link_reader.httpx, "Client",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(link_reader, "is_safe_url", lambda url: "private.test" not in url)


def _html(body):
    return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, content=body.encode("utf-8"))


def test_fetch_extracts_visible_text(monkeypatch):
    body = "<title>Аналитик</title><nav>Меню</nav><script>var x</script><p>" + "Требования к кандидату. " * 20 + "</p>"
    _serve(monkeypatch, lambda request: _html(body))
    text = link_reader.fetch_page_text(URL)
    assert "Аналитик" in text and "Требования" in text and "Меню" not in text and "var x" not in text


def test_fetch_rejects_empty_js_shell(monkeypatch):
    _serve(monkeypatch, lambda request: _html('<title>App</title><div id="root"></div><script>big()</script>'))
    assert link_reader.fetch_page_text(URL) is None


def test_fetch_follows_redirect(monkeypatch):
    def handler(request):
        if request.url.path == "/job":
            return httpx.Response(302, headers={"location": "/final"})
        return _html("<p>" + "Текст вакансии. " * 30 + "</p>")

    _serve(monkeypatch, handler)
    assert "Текст вакансии" in link_reader.fetch_page_text(URL)


def test_fetch_blocks_redirect_to_private_address(monkeypatch):
    requested = []

    def handler(request):
        requested.append(request.url.host)
        return httpx.Response(302, headers={"location": "http://private.test/secret"})

    _serve(monkeypatch, handler)
    assert link_reader.fetch_page_text(URL) is None
    assert requested == ["example.com"]


@pytest.mark.parametrize("response,expected", [
    ("Релевантна: да", True),
    ("Релевантна: Да.", True),
    ("Релевантна: нет", False),
    ("да", True),
    ("Да, это вакансия", True),
    ("нет", False),
    ("да или нет", False),
    ("Не могу определить", False),
])
def test_is_relevant_page_parsing(monkeypatch, response, expected):
    monkeypatch.setattr(analyst.gigachat_client, "chat", lambda **kwargs: response)
    assert analyst.is_relevant_page(PAGE) is expected


@pytest.fixture
def start_session(monkeypatch):
    """Запускает интервью с подменой сети и LLM, возвращает текст для build_plan и счётчики вызовов."""
    def run(text, page=PAGE, relevant=True):
        calls = {"fetch": 0, "relevance": 0, "plan_input": None}

        def fake_fetch(url):
            calls["fetch"] += 1
            return page

        def fake_relevant(page_text, user_text):
            calls["relevance"] += 1
            return relevant

        def fake_plan(vacancy):
            calls["plan_input"] = vacancy
            return InterviewPlan(role="Аналитик", level="middle", topics=["a", "b", "c", "d", "e"])

        monkeypatch.setattr(link_reader, "fetch_page_text", fake_fetch)
        monkeypatch.setattr(analyst, "is_relevant_page", fake_relevant)
        monkeypatch.setattr(analyst, "build_plan", fake_plan)
        monkeypatch.setattr(orchestrator.interviewer, "next_question", lambda *args, **kwargs: "Вопрос")
        assert InterviewSession().start(text) == "Вопрос"
        return calls

    return run


def test_without_link_skips_browser_and_relevance(start_session):
    calls = start_session("Текст вакансии")
    assert calls == {"fetch": 0, "relevance": 0, "plan_input": "Текст вакансии"}


def test_relevant_link_adds_page_to_text(start_session):
    plan_input = start_session(f"Текст вакансии {URL}")["plan_input"]
    assert "Текст вакансии" in plan_input and PAGE in plan_input and URL not in plan_input


def test_link_only_uses_page(start_session):
    assert start_session(URL)["plan_input"] == PAGE


def test_irrelevant_link_is_ignored(start_session):
    assert start_session(f"Текст вакансии {URL}", relevant=False)["plan_input"] == "Текст вакансии"


def test_failed_fetch_skips_relevance(start_session):
    calls = start_session(f"Текст вакансии {URL}", page=None)
    assert calls["relevance"] == 0 and calls["plan_input"] == "Текст вакансии"


@pytest.mark.parametrize("page,relevant", [(None, True), (PAGE, False)])
def test_link_only_without_usable_page_raises(start_session, page, relevant):
    with pytest.raises(ValueError, match=LINK_UNUSABLE_MESSAGE):
        start_session(URL, page=page, relevant=relevant)
