from io import BytesIO

from pypdf import PdfReader

from app.report_pdf import build_report_pdf


def test_report_preserves_russian_text_and_markdown_content():
    report = """### Что получилось хорошо
- **Конкретика**: вы описали результат.
- *Структура*: понятный ответ.

### План подготовки на неделю
1. День 1: повторить SQL.
2. День 2: разобрать `JOIN` и условие a < b & c > d.
"""
    data = build_report_pdf(report, "Разработчик Python", "Junior")
    assert data.startswith(b"%PDF-")
    reader = PdfReader(BytesIO(data))
    text = "\n".join(page.extract_text() for page in reader.pages)
    for expected in ("Итоговый разбор интервью", "Разработчик Python", "Junior",
                     "Что получилось хорошо", "Конкретика", "Структура",
                     "День 2", "JOIN", "a < b & c > d"):
        assert expected in text
    assert "**" not in text
    assert "###" not in text
    assert any("/FontFile2" in font.get_object()["/FontDescriptor"].get_object()
               for font in reader.pages[0]["/Resources"]["/Font"].values()
               if "/FontDescriptor" in font.get_object())


def test_long_report_spans_pages_without_losing_the_end():
    report = "### Рекомендации\n\n" + "Подробный совет по подготовке. " * 2500
    report += "\n\nПоследняя рекомендация."
    reader = PdfReader(BytesIO(build_report_pdf(report)))
    assert len(reader.pages) > 1
    assert "Последняя рекомендация." in reader.pages[-1].extract_text()


def test_html_is_literal_and_does_not_load_external_resources():
    report = '<img src="file:///missing.png"/>\n\n<script>alert(1)</script>'
    reader = PdfReader(BytesIO(build_report_pdf(report)))
    text = reader.pages[0].extract_text()
    assert '<img src="file:///missing.png"/>' in text
    assert "<script>alert(1)</script>" in text
