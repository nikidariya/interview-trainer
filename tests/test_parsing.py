from app.parsing import parse_key_values, parse_numbered_list, parse_score


def test_numbered_list_handles_different_markers():
    text = "Вот план:\n1. Python\n2) SQL\n- Опыт работы\nИтого"
    assert parse_numbered_list(text) == ["Python", "SQL", "Опыт работы"]


def test_key_values_ignores_extra_text():
    text = "Оценка ниже.\nКонкретика: 4\nструктура - 3\nКомментарий: мало примеров"
    result = parse_key_values(text, ["Конкретика", "Структура", "Комментарий"])
    assert result == {"Конкретика": "4", "Структура": "3", "Комментарий": "мало примеров"}


def test_missing_key_is_absent():
    assert parse_key_values("Конкретика: 4", ["Структура"]) == {}


def test_parse_score_with_fallbacks():
    assert parse_score("4 из 5") == 4
    assert parse_score(None) == 3
    assert parse_score("нет числа") == 3
    assert parse_score("10") == 5
