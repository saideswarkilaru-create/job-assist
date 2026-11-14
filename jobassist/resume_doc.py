"""Resume files: import any format to Word, and read a resume's structure (offline).

- to_docx():  .docx copied; .pdf / .doc converted once (Microsoft Word if installed, else pdf2docx for PDFs)
- parse():    name, contact lines, hyperlinks, and sections in the user's own order:
              experience/projects -> entries (header lines + bullets), skills -> (label, items) lines,
              others -> plain lines. Used by the resume check and by resume designs.
"""
from __future__ import annotations

import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from docx import Document

from .tailor import _LABEL, is_bullet, section_of, walk

SUPPORTED = (".docx", ".pdf", ".doc")
BULLET_GLYPHS = "•-–*▪◦●‣"
_BULLET_PREFIX = re.compile(rf"^\s*[{re.escape(BULLET_GLYPHS)}]\s*|^\s*o\s+(?=[A-Z])")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
URL = re.compile(r"(?:https?://|www\.)\S+|(?:linkedin\.com|github\.com)/\S+", re.I)


# ------------------------------------------------------------------ import
def _word_convert(src: Path, dst: Path) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        try:
            doc = word.Documents.Open(str(src.resolve()), ConfirmConversions=False, ReadOnly=True, AddToRecentFiles=False)
            doc.SaveAs2(str(dst.resolve()), FileFormat=16)  # wdFormatDocumentDefault (.docx)
            doc.Close(False)
        finally:
            word.Quit()
        return dst.exists() and dst.stat().st_size > 0
    except Exception:
        return False


def _pdf2docx(src: Path, dst: Path) -> bool:
    try:
        from pdf2docx import Converter

        cv = Converter(str(src))
        try:
            cv.convert(str(dst))
        finally:
            cv.close()
        return dst.exists() and dst.stat().st_size > 0
    except Exception:
        return False


def to_docx(src: Path, dst: Path) -> str:
    """Make `dst` a .docx version of `src`. Returns how: docx | word | pdf2docx. Raises if impossible."""
    ext = src.suffix.lower()
    if ext == ".docx":
        shutil.copyfile(src, dst)
        return "docx"
    if ext not in SUPPORTED:
        raise ValueError("Please upload a Word (.docx / .doc) or PDF file.")
    if _word_convert(src, dst):
        return "word"
    if ext == ".pdf" and _pdf2docx(src, dst):
        return "pdf2docx"
    if ext == ".doc":
        raise ValueError("Old .doc files need Microsoft Word to convert. Save it as .docx (File > Save As) and upload that.")
    raise ValueError("Could not read that PDF. If it is a scanned image, upload the Word version instead.")


# ------------------------------------------------------------------ structure
@dataclass
class Link:
    text: str
    url: str


@dataclass
class Entry:
    header: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)


@dataclass
class Section:
    kind: str
    title: str
    lines: list[str] = field(default_factory=list)          # summary / education / other
    entries: list[Entry] = field(default_factory=list)      # experience / projects
    skills: list[tuple[str, str]] = field(default_factory=list)  # (label, items)


@dataclass
class ResumeDoc:
    name: str = ""
    contact: list[str] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    tables: int = 0
    text_boxes: int = 0
    images: int = 0
    header_footer_text: str = ""

    def section(self, kind: str) -> Section | None:
        return next((s for s in self.sections if s.kind == kind), None)


def clean_bullet(text: str) -> str:
    return _BULLET_PREFIX.sub("", text).strip()


def _is_bulletish(p) -> bool:
    return is_bullet(p) or bool(_BULLET_PREFIX.match(p.text))


def parse(path: Path) -> ResumeDoc:
    doc = Document(str(path))
    rd = ResumeDoc()
    body = doc.element.body
    rd.tables = len(doc.tables)
    rd.text_boxes = len(body.xpath(".//w:txbxContent"))
    rd.images = len(body.xpath(".//w:drawing")) + len(body.xpath(".//w:pict"))
    hf = []
    for s in doc.sections:
        for part in (s.header, s.footer):
            hf += [p.text for p in part.paragraphs if p.text.strip()]
    rd.header_footer_text = "\n".join(hf)

    for p in doc.paragraphs:
        for h in p.hyperlinks:
            url = h.address or ""
            if url and h.text.strip():
                rd.links.append(Link(h.text.strip(), url))

    current: Section | None = None
    for sec, kind, obj in walk(doc):
        if kind == "heading":
            current = Section(sec, obj.text.strip())
            rd.sections.append(current)
            continue
        if kind == "table":
            rows = []
            for row in obj.rows:
                cells, seen = [], set()
                for c in row.cells:
                    if id(c._tc) not in seen and c.text.strip():
                        seen.add(id(c._tc))
                        cells.append(c.text.strip())
                if cells:
                    rows.append(cells)
            if current and current.kind == "skills":
                current.skills += [(r[0], ", ".join(r[1:])) if len(r) > 1 else ("", r[0]) for r in rows]
            elif current:
                current.lines += [" | ".join(r) for r in rows]
            else:
                rd.contact += [" | ".join(r) for r in rows]
            continue
        text = obj.text.strip()
        if not text:
            continue
        if current is None:  # header block before the first section
            if not rd.name and len(text.split()) <= 5 and not re.search(r"[\d@|:]", text):
                rd.name = text
            else:
                rd.contact.append(text)
            continue
        if current.kind in ("experience", "projects"):
            if _is_bulletish(obj):
                if not current.entries:
                    current.entries.append(Entry())
                current.entries[-1].bullets.append(clean_bullet(text))
            else:
                if not current.entries or current.entries[-1].bullets:
                    current.entries.append(Entry())
                current.entries[-1].header.append(text)
        elif current.kind == "skills":
            m = _LABEL.match(text)
            current.skills.append((m.group("label").strip(" :|"), m.group("items").strip()) if m else ("", clean_bullet(text)))
        else:
            current.lines.append(clean_bullet(text) if _is_bulletish(obj) else text)
    return rd


def all_text(rd: ResumeDoc) -> str:
    out = [rd.name, *rd.contact]
    for s in rd.sections:
        out.append(s.title)
        out += s.lines
        out += [f"{l}: {i}" if l else i for l, i in s.skills]
        for e in s.entries:
            out += e.header + e.bullets
    return "\n".join(x for x in out if x)
