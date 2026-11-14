"""Resume designs: the user's own content re-laid-out in clean, ATS-friendly Word layouts.

Rules: same words, same order of sections, nothing added or dropped (checked by same_content()).
Contact links (LinkedIn, GitHub, portfolio, email) become real clickable hyperlinks. The user previews
each design as a PDF and picks one; it is saved as a NEW base resume, the original stays as it was.

Designs (all single-column, standard fonts, no tables / text boxes / images, so ATS read them fully):
  classic  - centred name, serif headings with a rule, the most traditional look
  modern   - left-aligned name in navy, clean sans-serif, roomy spacing
  compact  - tight margins and spacing to fit more on one page (good for 0-3 years of experience)
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from .resume_doc import EMAIL, URL, ResumeDoc, Link, all_text

DESIGNS = {
    "classic": {"label": "Classic", "about": "Centred name, serif headings with a line under each. Traditional and safe for any employer.",
                "font": "Georgia", "size": 10.5, "name_size": 18, "heading_size": 11.5, "color": RGBColor(0x11, 0x11, 0x11),
                "align_name": "center", "margins": 0.75, "space_after": 2, "heading_upper": True, "rule": True},
    "modern": {"label": "Modern", "about": "Left-aligned name in navy, clean sans-serif font, roomy spacing. Reads well on screen.",
               "font": "Calibri", "size": 11, "name_size": 22, "heading_size": 12.5, "color": RGBColor(0x1A, 0x3A, 0x6B),
               "align_name": "left", "margins": 0.8, "space_after": 3, "heading_upper": False, "rule": True},
    "compact": {"label": "Compact", "about": "Tighter margins and spacing to fit more on one page. Good for 0–3 years of experience.",
                "font": "Arial", "size": 9.5, "name_size": 16, "heading_size": 10.5, "color": RGBColor(0x22, 0x22, 0x22),
                "align_name": "left", "margins": 0.5, "space_after": 1, "heading_upper": True, "rule": False},
}


# ------------------------------------------------------------------ low-level helpers
def _set_font(run, font: str, size: float, bold=False, italic=False, color=None):
    run.font.name = font
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font)
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    if color is not None:
        run.font.color.rgb = color


def add_hyperlink(paragraph, text: str, url: str, font: str, size: float, color=RGBColor(0x1A, 0x3A, 0x6B)):
    if url.startswith("www."):
        url = "https://" + url
    if EMAIL.fullmatch(text) and not url.startswith("mailto:"):
        url = "mailto:" + text
    r_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), r_id)
    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    fonts = OxmlElement("w:rFonts")
    fonts.set(qn("w:ascii"), font)
    fonts.set(qn("w:hAnsi"), font)
    rpr.append(fonts)
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), str(int(size * 2)))
    rpr.append(sz)
    col = OxmlElement("w:color")
    col.set(qn("w:val"), str(color))
    rpr.append(col)
    u = OxmlElement("w:u")
    u.set(qn("w:val"), "single")
    rpr.append(u)
    run.append(rpr)
    t = OxmlElement("w:t")
    t.text = text
    t.set(qn("xml:space"), "preserve")
    run.append(t)
    link.append(run)
    paragraph._p.append(link)


def write_text(paragraph, text: str, links: list[Link], d: dict, bold=False, italic=False):
    """Write text; any part that was a hyperlink in the original (or is an email / URL) stays clickable."""
    spans = []
    for l in links:
        for m in re.finditer(re.escape(l.text), text):
            spans.append((m.start(), m.end(), l.url))
    for rx in (EMAIL, URL):
        for m in rx.finditer(text):
            if not any(a <= m.start() < b for a, b, _ in spans):
                spans.append((m.start(), m.end(), m.group(0)))
    spans.sort()
    pos = 0
    for a, b, url in spans:
        if a < pos:
            continue
        if a > pos:
            _set_font(paragraph.add_run(text[pos:a]), d["font"], d["size"], bold, italic)
        add_hyperlink(paragraph, text[a:b], url, d["font"], d["size"])
        pos = b
    if pos < len(text):
        _set_font(paragraph.add_run(text[pos:]), d["font"], d["size"], bold, italic)


def _spacing(p, after: float, before: float = 0):
    pf = p.paragraph_format
    pf.space_after = Pt(after)
    pf.space_before = Pt(before)
    pf.line_spacing = 1.05


def _rule(p, color="999999"):
    ppr = p._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for k, v in (("w:val", "single"), ("w:sz", "6"), ("w:space", "1"), ("w:color", color)):
        bottom.set(qn(k), v)
    bdr.append(bottom)
    ppr.append(bdr)


# ------------------------------------------------------------------ render
def render(rd: ResumeDoc, design: str, out: Path) -> Path:
    d = DESIGNS[design]
    doc = Document()
    for s in doc.sections:
        s.left_margin = s.right_margin = Inches(d["margins"])
        s.top_margin = s.bottom_margin = Inches(max(0.45, d["margins"] - 0.15))
    normal = doc.styles["Normal"]
    normal.font.name = d["font"]
    normal.font.size = Pt(d["size"])

    if rd.name:
        p = doc.add_paragraph()
        _set_font(p.add_run(rd.name), d["font"], d["name_size"], bold=True, color=d["color"])
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if d["align_name"] == "center" else WD_ALIGN_PARAGRAPH.LEFT
        _spacing(p, 2)
    for line in rd.contact:
        p = doc.add_paragraph()
        write_text(p, line, rd.links, d)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if d["align_name"] == "center" else WD_ALIGN_PARAGRAPH.LEFT
        _spacing(p, 1)

    for sec in rd.sections:
        h = doc.add_paragraph()
        _set_font(h.add_run(sec.title.upper() if d["heading_upper"] else sec.title.strip(": ")),
                  d["font"], d["heading_size"], bold=True, color=d["color"])
        _spacing(h, 3, before=d["space_after"] * 3 + 4)
        if d["rule"]:
            _rule(h)
        for line in sec.lines:
            p = doc.add_paragraph()
            write_text(p, line, rd.links, d)
            _spacing(p, d["space_after"])
        for label, items in sec.skills:
            p = doc.add_paragraph()
            if label:
                _set_font(p.add_run(label + ": "), d["font"], d["size"], bold=True)
            write_text(p, items, rd.links, d)
            _spacing(p, d["space_after"])
        for e in sec.entries:
            for i, line in enumerate(e.header):
                p = doc.add_paragraph()
                write_text(p, line, rd.links, d, bold=(i == 0), italic=(i > 0))
                _spacing(p, 0 if i < len(e.header) - 1 else 1, before=(d["space_after"] + 2) if i == 0 else 0)
            for b in e.bullets:
                p = doc.add_paragraph(style="List Bullet")
                write_text(p, b, rd.links, d)
                _spacing(p, d["space_after"])
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return out


# ------------------------------------------------------------------ honesty
def same_content(original_text: str, new_text: str) -> tuple[bool, str]:
    """Every word of the original present, and no new words except upper-cased headings."""
    def words(t):
        return Counter(w.lower() for w in re.findall(r"[A-Za-z0-9+#.]+", t) if w.strip("."))
    a, b = words(original_text), words(new_text)
    missing, extra = a - b, b - a
    if missing:
        return False, "would drop: " + ", ".join(list(missing)[:8])
    if extra:
        return False, "would add: " + ", ".join(list(extra)[:8])
    return True, "ok"


def build_all(rd: ResumeDoc, original_text: str, folder: Path, stem: str) -> list[dict]:
    """Render every design into `folder`; return those that keep the content exactly."""
    from .resume_text import docx_to_text

    out = []
    for key, d in DESIGNS.items():
        path = render(rd, key, folder / f"{stem}_{key}.docx")
        # compare with the ORIGINAL file's text, so a parsing slip can't silently drop content
        ok, why = same_content(original_text, docx_to_text(path))
        out.append({"key": key, "label": d["label"], "about": d["about"], "docx": str(path), "ok": ok, "check": why})
    return out
