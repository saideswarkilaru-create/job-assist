"""Word -> PDF, trying what's available on this PC, best quality first:
  1. Microsoft Word (exact layout)          via docx2pdf (Word COM)
  2. LibreOffice (very close layout)        soffice --headless
  3. Built-in: mammoth (docx -> clean HTML) + the app's browser prints it to PDF (works everywhere)

The browser step runs in its own process (python -m jobassist.pdf), so it never clashes with a
search run that already has a browser open.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import paths

_CSS = """
@page { size: Letter; margin: 0.6in 0.7in; }
body { font-family: Calibri, Arial, sans-serif; font-size: 10.5pt; line-height: 1.35; color: #111; }
h1, h2, h3 { margin: 10px 0 4px; } h1 { font-size: 17pt; } h2 { font-size: 12.5pt; border-bottom: 1px solid #999; }
p { margin: 3px 0; } ul { margin: 2px 0 6px 18px; padding: 0; } li { margin: 1px 0; }
table { border-collapse: collapse; width: 100%; } td { vertical-align: top; padding: 1px 6px 1px 0; }
strong { font-weight: 700; }
"""


def _word(src: Path, dst: Path) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import pythoncom  # noqa: F401  (part of pywin32, installed with docx2pdf)
        from docx2pdf import convert
    except Exception:
        return False
    try:
        import pythoncom
        pythoncom.CoInitialize()
        convert(str(src), str(dst))
        return dst.exists() and dst.stat().st_size > 0
    except Exception:
        return False


def _libreoffice(src: Path, dst: Path) -> bool:
    exe = shutil.which("soffice") or next((p for p in (
        Path(os.environ.get("ProgramFiles", "")) / "LibreOffice/program/soffice.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "LibreOffice/program/soffice.exe") if p.exists()), None)
    if not exe:
        return False
    try:
        subprocess.run([str(exe), "--headless", "--convert-to", "pdf", "--outdir", str(dst.parent), str(src)],
                       check=True, timeout=120, capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        produced = dst.parent / (src.stem + ".pdf")
        if produced != dst and produced.exists():
            produced.replace(dst)
        return dst.exists()
    except Exception:
        return False


def html_for(src: Path) -> str:
    import mammoth

    with open(src, "rb") as f:
        body = mammoth.convert_to_html(f).value
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{_CSS}</style></head><body>{body}</body></html>"


def _browser(src: Path, dst: Path, channel: str) -> bool:
    proc = subprocess.run([sys.executable, "-m", "jobassist.pdf", str(src), str(dst), channel],
                          cwd=str(paths.ROOT), capture_output=True, text=True, timeout=180,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return proc.returncode == 0 and dst.exists()


def docx_to_pdf(src: Path, dst: Path, channel: str = "chrome", methods=("word", "libreoffice", "browser")) -> str:
    """Convert and return the method used. Raises if nothing worked."""
    dst.unlink(missing_ok=True)
    for m in methods:
        ok = {"word": lambda: _word(src, dst), "libreoffice": lambda: _libreoffice(src, dst),
              "browser": lambda: _browser(src, dst, channel)}[m]()
        if ok:
            return m
    raise RuntimeError("No PDF converter worked (Word, LibreOffice and the browser all failed).")


def folder_to_pdf(files: list[Path], channel: str = "chrome") -> str:
    """Convert several .docx in one go (one Word session when Word is installed). Returns the method."""
    if sys.platform == "win32" and files:
        try:
            import pythoncom
            from docx2pdf import convert

            pythoncom.CoInitialize()
            folder = files[0].parent
            convert(str(folder), str(folder))
            if all(f.with_suffix(".pdf").exists() for f in files):
                return "word"
        except Exception:
            pass
    method = ""
    for f in files:
        method = docx_to_pdf(f, f.with_suffix(".pdf"), channel, methods=("libreoffice", "browser"))
    return method


def _print_with_browser(src: Path, dst: Path, channel: str) -> None:
    from playwright.sync_api import sync_playwright

    html = html_for(src)
    with sync_playwright() as p:
        browser = None
        for ch in [channel, "chrome", "msedge", "chromium"]:
            try:
                browser = p.chromium.launch(headless=True, **({} if ch == "chromium" else {"channel": ch}))
                break
            except Exception:
                continue
        if browser is None:
            raise RuntimeError("no browser available")
        page = browser.new_page()
        page.set_content(html, wait_until="load")
        page.pdf(path=str(dst), format="Letter", print_background=True,
                 margin={"top": "0.6in", "bottom": "0.6in", "left": "0.7in", "right": "0.7in"})
        browser.close()


if __name__ == "__main__":
    _print_with_browser(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "chrome")
