"""PDF and DOCX export for generated CVs and letters.

The stored ``content_json`` is the source of truth so users can edit a document
in the preview and export exactly what they see. Arabic output is shaped with
``arabic-reshaper`` + ``python-bidi`` and laid out right-to-left.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

import arabic_reshaper
from bidi.algorithm import get_display
from docx import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.models import Document

# Fonts are resolved from the host. Arial/Tahoma cover Latin and Arabic on
# Windows; DejaVu is the usual Linux fallback. If no TTF is found the PDF still
# renders Latin with Helvetica (Arabic glyphs would be missing).
_FONT_CANDIDATES = {
    "regular": [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/tahoma.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ],
    "bold": [
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("C:/Windows/Fonts/tahomabd.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ],
}
_REGISTERED: dict[str, str] = {}


def _font(kind: str) -> str:
    if kind in _REGISTERED:
        return _REGISTERED[kind]
    for path in _FONT_CANDIDATES[kind]:
        if path.exists():
            name = f"EJP-{kind}"
            try:
                pdfmetrics.registerFont(TTFont(name, str(path)))
                _REGISTERED[kind] = name
                return name
            except Exception:  # pragma: no cover - corrupt font file
                continue
    fallback = "Helvetica-Bold" if kind == "bold" else "Helvetica"
    _REGISTERED[kind] = fallback
    return fallback


def is_rtl_language(language: str | None) -> bool:
    return (language or "en").split("-")[0].lower() in {"ar", "fa", "he", "ur"}


def _visual(text: str) -> str:
    """Shape and reorder Arabic for non-shaping renderers."""
    if not text:
        return ""
    try:
        return get_display(arabic_reshaper.reshape(str(text)))
    except Exception:  # pragma: no cover - defensive
        return str(text)


def safe_filename(title: str, language: str, ext: str) -> str:
    stem = re.sub(r"[^\w\u0600-\u06FF-]+", "-", (title or "document").strip()).strip("-")
    stem = re.sub(r"-{2,}", "-", stem)[:80] or "document"
    return f"{stem}-{language or 'en'}.{ext}"


def _payload(doc: Document) -> dict[str, Any]:
    data = doc.content_json or {}
    return data if isinstance(data, dict) else {}


def _contact_line(contact: dict[str, str]) -> str:
    bits = [contact.get("email", ""), contact.get("phone", ""), contact.get("location", "")]
    return " · ".join([b for b in bits if b])


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def _edited_lines(doc: Document) -> list[str]:
    return (doc.content_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _render_edited_pdf(doc: Document) -> bytes:
    """Export user-edited plain text. Keeps the layout simple and predictable."""
    rtl = is_rtl_language(doc.language)
    base = ParagraphStyle(
        "ejp-edited",
        fontName=_font("regular"),
        fontSize=10.5,
        leading=15,
        alignment=TA_RIGHT if rtl else TA_LEFT,
        spaceAfter=3,
        wordWrap="RTL" if rtl else None,
    )
    heading = ParagraphStyle("ejp-edited-h", parent=base, fontName=_font("bold"), fontSize=11, spaceBefore=6)
    name_style = ParagraphStyle("ejp-edited-name", parent=base, fontName=_font("bold"), fontSize=18, leading=22, spaceAfter=2)

    buffer = io.BytesIO()
    template = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm, title=doc.title,
    )
    story: list = []
    lines = _edited_lines(doc)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            story.append(Spacer(1, 5))
            continue
        value = _visual(stripped) if rtl else stripped
        value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if index == 0 and len(stripped) < 60:
            story.append(Paragraph(value, name_style))
        elif len(stripped) < 48 and (stripped.isupper() or stripped.endswith(":")) and not stripped.startswith("•"):
            story.append(Paragraph(value, heading))
        else:
            story.append(Paragraph(value, base))
    template.build(story)
    return buffer.getvalue()


def _render_edited_docx(doc: Document) -> bytes:
    rtl = is_rtl_language(doc.language)
    document = DocxDocument()
    normal = document.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(10.5)
    for index, line in enumerate(_edited_lines(doc)):
        stripped = line.strip()
        if not stripped:
            document.add_paragraph()
            continue
        if index == 0 and len(stripped) < 60:
            _docx_para(document, stripped, bold=True, size=17, rtl=rtl, space_after=4)
        elif len(stripped) < 48 and (stripped.isupper() or stripped.endswith(":")) and not stripped.startswith("•"):
            _docx_para(document, stripped, bold=True, size=11, rtl=rtl, space_after=3)
        else:
            _docx_para(document, stripped, rtl=rtl, space_after=2)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def render_pdf(doc: Document) -> bytes:
    payload = _payload(doc)
    if payload.get("edited") and (doc.content_text or "").strip():
        return _render_edited_pdf(doc)
    rtl = is_rtl_language(doc.language)
    contact = payload.get("contact") or {}
    body_font = _font("regular")
    bold_font = _font("bold")

    base = ParagraphStyle(
        "ejp-body",
        fontName=body_font,
        fontSize=10.5,
        leading=15,
        alignment=TA_RIGHT if rtl else TA_LEFT,
        spaceAfter=4,
        wordWrap="RTL" if rtl else None,
    )
    heading = ParagraphStyle(
        "ejp-heading", parent=base, fontName=bold_font, fontSize=11, spaceBefore=10, spaceAfter=5
    )
    name_style = ParagraphStyle(
        "ejp-name", parent=base, fontName=bold_font, fontSize=19, leading=23, spaceAfter=2
    )
    small = ParagraphStyle("ejp-small", parent=base, fontSize=9, leading=13, spaceAfter=2)

    buffer = io.BytesIO()
    template = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=doc.title,
        author=str(contact.get("full_name") or ""),
    )
    story: list = []

    def para(text: str, style=base):
        if not text:
            return
        value = _visual(text) if rtl else str(text)
        # Escape the few characters ReportLab's mini-markup treats specially.
        value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        story.append(Paragraph(value, style))

    full_name = str(contact.get("full_name") or "")
    if full_name:
        para(full_name, name_style)
    contact_line = _contact_line(contact)
    if contact_line:
        para(contact_line, small)

    if doc.doc_type == "cv":
        if payload.get("headline"):
            para(payload["headline"], heading)
        if payload.get("summary"):
            para(payload["summary"])
        experience = payload.get("experience") or []
        if experience:
            para("EXPERIENCE" if not rtl else "الخبرة", heading)
            for row in experience:
                header = " — ".join(
                    [x for x in (row.get("title"), row.get("company")) if x]
                )
                period = " – ".join([x for x in (row.get("start"), row.get("end")) if x])
                if period:
                    header = f"{header} ({period})"
                para(header, heading)
                for bullet in row.get("bullets") or []:
                    para(f"• {bullet}")
                story.append(Spacer(1, 4))
        education = payload.get("education") or []
        if education:
            para("EDUCATION" if not rtl else "التعليم", heading)
            for row in education:
                para(
                    " — ".join(
                        [x for x in (row.get("degree"), row.get("institution"), row.get("year")) if x]
                    )
                )
        for key, label in (
            ("skills", "SKILLS" if not rtl else "المهارات"),
            ("languages", "LANGUAGES" if not rtl else "اللغات"),
            ("certifications", "CERTIFICATIONS" if not rtl else "الشهادات"),
        ):
            values = payload.get(key) or []
            if values:
                para(label, heading)
                para(", ".join(str(v) for v in values))
        projects = payload.get("projects") or []
        if projects:
            para("PROJECTS" if not rtl else "المشاريع", heading)
            for row in projects:
                para(f"{row.get('name', '')}: {row.get('description', '')}")
        if payload.get("relocation_note"):
            para(payload["relocation_note"])
    else:
        if payload.get("greeting"):
            para(payload["greeting"])
        if payload.get("opening"):
            para(payload["opening"])
        for paragraph in payload.get("body") or []:
            para(paragraph)
        if payload.get("relocation_paragraph"):
            para(payload["relocation_paragraph"])
        if payload.get("closing"):
            para(payload["closing"])
        signoff = payload.get("signoff") or ""
        if signoff:
            para(signoff)
        if full_name:
            para(full_name, heading)

    template.build(story)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------

def _set_rtl(paragraph) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    bidi = OxmlElement("w:bidi")
    p_pr.append(bidi)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT


def _docx_run(paragraph, text: str, *, bold: bool = False, size: float = 10.5, rtl: bool = False):
    run = paragraph.add_run(str(text))
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = "Arial"
    r_pr = run._element.get_or_add_rPr()
    fonts = r_pr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        r_pr.append(fonts)
    fonts.set(qn("w:cs"), "Arial")
    if rtl:
        rtl_el = OxmlElement("w:rtl")
        r_pr.append(rtl_el)
    return run


def _docx_para(doc, text: str, *, bold=False, size=10.5, rtl=False, space_after=4, color=None):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(space_after)
    if rtl:
        _set_rtl(paragraph)
    run = _docx_run(paragraph, text, bold=bold, size=size, rtl=rtl)
    if color:
        run.font.color.rgb = RGBColor(*color)
    return paragraph


def render_docx(doc: Document) -> bytes:
    payload = _payload(doc)
    if payload.get("edited") and (doc.content_text or "").strip():
        return _render_edited_docx(doc)
    rtl = is_rtl_language(doc.language)
    contact = payload.get("contact") or {}

    document = DocxDocument()
    section = document.sections[0]
    section.top_margin = Pt(50)
    section.bottom_margin = Pt(50)
    section.left_margin = Pt(55)
    section.right_margin = Pt(55)

    normal = document.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(10.5)

    full_name = str(contact.get("full_name") or "")
    if full_name:
        _docx_para(document, full_name, bold=True, size=18, rtl=rtl, space_after=2)
    contact_line = _contact_line(contact)
    if contact_line:
        _docx_para(document, contact_line, size=9, rtl=rtl, space_after=8, color=(0x55, 0x55, 0x55))

    def heading(text: str):
        _docx_para(document, text, bold=True, size=11, rtl=rtl, space_after=3)

    if doc.doc_type == "cv":
        if payload.get("headline"):
            heading(payload["headline"])
        if payload.get("summary"):
            _docx_para(document, payload["summary"], rtl=rtl, space_after=8)
        experience = payload.get("experience") or []
        if experience:
            heading("الخبرة" if rtl else "EXPERIENCE")
            for row in experience:
                header = " — ".join([x for x in (row.get("title"), row.get("company")) if x])
                period = " – ".join([x for x in (row.get("start"), row.get("end")) if x])
                if period:
                    header = f"{header} ({period})"
                _docx_para(document, header, bold=True, size=10.5, rtl=rtl, space_after=2)
                for bullet in row.get("bullets") or []:
                    _docx_para(document, f"• {bullet}", rtl=rtl, space_after=1)
                document.add_paragraph()
        education = payload.get("education") or []
        if education:
            heading("التعليم" if rtl else "EDUCATION")
            for row in education:
                _docx_para(
                    document,
                    " — ".join(
                        [x for x in (row.get("degree"), row.get("institution"), row.get("year")) if x]
                    ),
                    rtl=rtl,
                    space_after=2,
                )
        for key, label in (
            ("skills", "المهارات" if rtl else "SKILLS"),
            ("languages", "اللغات" if rtl else "LANGUAGES"),
            ("certifications", "الشهادات" if rtl else "CERTIFICATIONS"),
        ):
            values = payload.get(key) or []
            if values:
                heading(label)
                _docx_para(document, ", ".join(str(v) for v in values), rtl=rtl)
        projects = payload.get("projects") or []
        if projects:
            heading("المشاريع" if rtl else "PROJECTS")
            for row in projects:
                _docx_para(
                    document, f"{row.get('name', '')}: {row.get('description', '')}", rtl=rtl, space_after=2
                )
        if payload.get("relocation_note"):
            _docx_para(document, payload["relocation_note"], rtl=rtl)
    else:
        if payload.get("greeting"):
            _docx_para(document, payload["greeting"], rtl=rtl)
        if payload.get("opening"):
            _docx_para(document, payload["opening"], rtl=rtl, space_after=6)
        for paragraph in payload.get("body") or []:
            _docx_para(document, paragraph, rtl=rtl, space_after=6)
        if payload.get("relocation_paragraph"):
            _docx_para(document, payload["relocation_paragraph"], rtl=rtl, space_after=6)
        if payload.get("closing"):
            _docx_para(document, payload["closing"], rtl=rtl, space_after=10)
        if payload.get("signoff"):
            _docx_para(document, payload["signoff"], rtl=rtl, space_after=2)
        if full_name:
            _docx_para(document, full_name, bold=True, rtl=rtl)

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
