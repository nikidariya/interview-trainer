"""Разбор ответов модели. Слабая модель часто отвечает не по формату, поэтому функции не падают."""
import re


def parse_numbered_list(text: str) -> list[str]:
    """Достаёт пункты вида "1. ...", "2) ..." или "- ..."; остальные строки игнорирует."""
    items = []
    for line in text.splitlines():
        match = re.match(r"^\s*(?:\d+[.)]|[-•*])\s*(.+?)\s*$", line)
        if match:
            items.append(match.group(1))
    return items


def parse_key_values(text: str, keys: list[str]) -> dict[str, str]:
    """Ищет строки "Ключ: значение" (допустимы ":" и "-"). Ненайденные ключи в результат не попадают."""
    result = {}
    for key in keys:
        match = re.search(rf"^\s*{re.escape(key)}\s*[:：-]\s*(.+?)\s*$", text,
                          re.IGNORECASE | re.MULTILINE)
        if match:
            result[key] = match.group(1)
    return result


def parse_score(value: str | None, default: int = 3, low: int = 1, high: int = 5) -> int:
    """Берёт первое число из строки и ограничивает диапазоном; если числа нет, возвращает default."""
    match = re.search(r"\d+", value or "")
    if not match:
        return default
    return max(low, min(high, int(match.group())))
