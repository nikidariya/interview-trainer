"""Чтение вакансии по ссылке: находит URL в тексте, скачивает HTML и достаёт из него текст.

JavaScript не выполняется: страницы, которые показывают текст только через него, считаются нечитаемыми.
"""
import ipaddress
import logging
import re
import socket
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

MIN_PAGE_CHARS = 200  # меньше обычно означает пустую оболочку, заглушку или форму входа
MAX_PAGE_CHARS = 6000
MAX_RESPONSE_BYTES = 2_000_000
MAX_REDIRECTS = 5
TIMEOUT_SECONDS = 15
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/136.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ru,en;q=0.8",
}

_URL_RE = re.compile(r"https?://[^\s<>\"'«»]+", re.IGNORECASE)


def extract_url(text: str) -> str | None:
    """Возвращает первую http(s)-ссылку из текста или None."""
    match = _URL_RE.search(text)
    if not match:
        return None
    return match.group().rstrip(".,;:!?)]}") or None


def is_safe_url(url: str) -> bool:
    """Разрешает только http(s)-адреса, которые ведут в публичный интернет.

    URL приходит от пользователя, поэтому запрос не должен достучаться до сервисов внутри сети.
    """
    try:
        parts = urlsplit(url)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            return False
        addresses = socket.getaddrinfo(parts.hostname, parts.port or None, proto=socket.IPPROTO_TCP)
    except (OSError, ValueError):
        return False
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0].split("%")[0])
        ip = getattr(ip, "ipv4_mapped", None) or ip
        if not ip.is_global:
            return False
    return bool(addresses)


def _html_to_text(html: bytes, encoding: str | None = None) -> str:
    soup = BeautifulSoup(html, "html.parser", from_encoding=encoding)
    for element in soup(["script", "style", "noscript", "template", "svg", "nav", "footer"]):
        element.decompose()
    lines = (" ".join(line.split()) for line in soup.get_text("\n").splitlines())
    return "\n".join(line for line in lines if line)


def _download_html(url: str) -> tuple[bytes, str | None] | None:
    """Скачивает страницу, проверяя каждый адрес в цепочке редиректов."""
    with httpx.Client(headers=HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            if not is_safe_url(url):
                return None
            with client.stream("GET", url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers["location"])
                    continue
                response.raise_for_status()
                if "html" not in response.headers.get("content-type", "html").lower():
                    return None
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        return None
                return bytes(body), response.charset_encoding
    return None


def fetch_page_text(url: str) -> str | None:
    """Возвращает текст страницы или None, если её не удалось прочитать."""
    try:
        downloaded = _download_html(url)
        if downloaded is None:
            return None
        text = _html_to_text(*downloaded)
    except Exception as error:  # сеть, таймаут, блокировка сайтом: ссылку просто не используем
        logger.warning("Не удалось прочитать страницу %s: %s", url, error)
        return None
    return text[:MAX_PAGE_CHARS] if len(text) >= MIN_PAGE_CHARS else None
