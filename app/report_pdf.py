"""Render the saved Markdown report as a portable PDF, entirely in memory."""
from functools import lru_cache
from html import escape
from io import BytesIO
from pathlib import Path

from markdown_it import MarkdownIt
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


@lru_cache(maxsize=1)
def _register_fonts() -> None:
    directory = Path(__file__).parent / "fonts"
    for suffix in ("", "-Bold", "-Oblique", "-BoldOblique"):
        name = f"DejaVuSans{suffix}"
        pdfmetrics.registerFont(TTFont(name, str(directory / f"{name}.ttf")))
    pdfmetrics.registerFontFamily(
        "DejaVuSans", normal="DejaVuSans", bold="DejaVuSans-Bold",
        italic="DejaVuSans-Oblique", boldItalic="DejaVuSans-BoldOblique",
    )


def _inline(tokens) -> str:
    # Only generate our own formatting tags: model/user HTML must remain text.
    tags = {"strong_open": "<b>", "strong_close": "</b>",
            "em_open": "<i>", "em_close": "</i>",
            "softbreak": " ", "hardbreak": "<br/>"}
    return "".join(tags.get(token.type, escape(token.content)) for token in tokens)


def build_report_pdf(report: str, role: str = "", level: str = "") -> bytes:
    """Export existing report text without calling the model or saving user data."""
    _register_fonts()
    body = ParagraphStyle("Body", fontName="DejaVuSans", fontSize=10,
                          leading=15, spaceAfter=7)
    heading = ParagraphStyle("Heading", parent=body, fontName="DejaVuSans-Bold",
                             fontSize=13, leading=18, spaceBefore=12, keepWithNext=True)
    title = ParagraphStyle("Title", parent=heading, fontSize=20, leading=26)
    story = [Paragraph("Итоговый разбор интервью", title)]
    if role or level:
        story.append(Paragraph(escape(" · ".join(filter(None, (role, level)))), body))
    story.append(Spacer(1, 5 * mm))
    lists = []
    bullet = None
    is_heading = False
    for token in MarkdownIt("commonmark", {"html": False}).parse(report):
        if token.type in ("bullet_list_open", "ordered_list_open"):
            lists.append(None if token.type == "bullet_list_open" else int(token.attrGet("start") or 1))
        elif token.type in ("bullet_list_close", "ordered_list_close"):
            lists.pop()
        elif token.type == "list_item_open":
            bullet = "•" if lists[-1] is None else f"{lists[-1]}."
            if lists[-1] is not None:
                lists[-1] += 1
        elif token.type == "list_item_close":
            bullet = None
        elif token.type == "heading_open":
            is_heading = True
        elif token.type == "heading_close":
            is_heading = False
        elif token.type in ("inline", "fence", "code_block"):
            text = (_inline(token.children or []) if token.type == "inline"
                    else escape(token.content).replace("\n", "<br/>"))
            style = heading if is_heading else body
            if lists:
                style = ParagraphStyle("List", parent=style, leftIndent=18 * len(lists),
                                       bulletIndent=18 * (len(lists) - 1),
                                       bulletFontName="DejaVuSans")
            story.append(Paragraph(text, style, bulletText=bullet))
            bullet = None

    def footer(canvas, doc):
        canvas.setFont("DejaVuSans", 9)
        canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, str(doc.page))

    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, rightMargin=20 * mm,
                                 leftMargin=20 * mm, topMargin=18 * mm,
                                 bottomMargin=20 * mm, title="Итоговый разбор интервью")
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
