"""Read plain text out of a .docx resume (paragraphs and tables, in document order)."""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


def docx_to_text(path: Path) -> str:
    doc = Document(str(path))
    lines: list[str] = []
    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            t = Paragraph(child, doc).text.strip()
            if t:
                lines.append(t)
        elif tag == "tbl":
            for row in Table(child, doc).rows:
                cells, seen = [], set()
                for c in row.cells:  # merged cells repeat; keep each once
                    t = c.text.strip()
                    if t and id(c._tc) not in seen:
                        seen.add(id(c._tc))
                        cells.append(t)
                if cells:
                    lines.append(" | ".join(cells))
    return "\n".join(lines)
