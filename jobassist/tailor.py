"""Tailored resumes: honest, format-preserving edits of the base .docx for one job.

What the built-in tailor does (offline, deterministic):
  1. Bullets: inside each job / project, bullets that mention this JD's skills move up. Bullets never
     move between jobs and are never changed.
  2. Skills section: skills the JD asks for move to the front of each line (optionally bold).
  3. Optional "Key skills for this role" line under the summary, listing only skills already in the resume.
Optional Claude rewording (Settings) rephrases bullets toward the JD's wording; each rewrite must pass
the bullet-level guard (no skill or number that the original bullet didn't have).

Honesty guard (always): the tailored document may not contain any skill or number that the base resume
doesn't, and (built-in mode) must contain exactly the same words apart from the key-skills line.
If the guard fails, the base resume is used unchanged and the report says why.
"""
from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from copy import deepcopy
from datetime import date
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from . import claude_cli, paths, skills
from .resume_text import docx_to_text
from .textutil import slug

KEY_SKILLS_LABEL = "Key skills for this role: "

_SECTIONS = [
    ("summary", r"(professional |career )?(summary|profile|objective|about me|overview)"),
    ("skills", r"(technical |key |core )?(skills|competencies|technologies|tech stack|technical proficienc\w*|skill set|"
               r"tools( & | and )technologies|skills( & | and )tools)( summary)?"),
    ("experience", r"(professional |work |relevant |industry )?(experience|employment( history)?|work history|internships?)"),
    ("projects", r"(academic |personal |key |selected )?projects?"),
    ("education", r"education|academics?|academic background"),
    ("other", r"certifications?|awards|achievements|publications|languages|interests|volunteer\w*|honors|activities"),
]
_SECTION_RX = [(name, re.compile(rf"^\W*(?:{rx})\W*$", re.I)) for name, rx in _SECTIONS]
_BULLET_CHARS = ("•", "-", "–", "*", "▪", "◦", "●", "‣", "o ", "", "", "", "", "")
_NUM = re.compile(r"\d+(?:[.,]\d+)?\s*%?")


# ------------------------------------------------------------------ document structure
def section_of(text: str) -> str | None:
    t = text.strip()
    if not t or len(t) > 45:
        return None
    for name, rx in _SECTION_RX:
        if rx.match(t):
            return name
    return None


def is_bullet(p: Paragraph) -> bool:
    ppr = p._p.pPr
    if ppr is not None and ppr.find(qn("w:numPr")) is not None:
        return True
    if "list" in (p.style.name or "").lower():
        return True
    return p.text.lstrip().startswith(_BULLET_CHARS)


def walk(doc):
    """Yield (section, kind, obj) for body paragraphs and tables in order. kind: heading|para|table."""
    current = None
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, doc)
            sec = section_of(p.text)
            if sec:
                current = sec
                yield sec, "heading", p
            else:
                yield current, "para", p
        elif tag == "tbl":
            yield current, "table", Table(child, doc)


# ------------------------------------------------------------------ relevance
def canonical_matched(analysis: dict, lib) -> list[str]:
    """Analysis 'matched' list mapped onto canonical skill names, strongest first."""
    out = []
    for m in analysis.get("matched") or []:
        for name in skills.find(str(m), lib) or {}:
            if name not in out:
                out.append(name)
    return out


def display_skills(matched: list[str]) -> list[str]:
    """Drop a generic name when its specific form is also listed ('Spring' when 'Spring Boot' is there)."""
    return [m for m in matched if not any(o != m and o.lower().startswith(m.lower() + " ") for o in matched)]


def _weights(matched: list[str]) -> dict[str, float]:
    return {name: max(0.3, 1.0 - 0.07 * i) for i, name in enumerate(matched)}


def relevance(text: str, weights: dict[str, float], lib) -> float:
    return sum(weights.get(n, 0.0) for n in skills.find(text, lib))


# ------------------------------------------------------------------ edits
def reorder_bullets(doc, weights, lib, report) -> None:
    blocks, cur = [], []
    headings_seen = False
    for sec, kind, obj in walk(doc):
        headings_seen = headings_seen or kind == "heading"
        in_scope = sec in ("experience", "projects") or (sec is None and not headings_seen)
        if kind == "para" and in_scope and obj.text.strip() and is_bullet(obj):
            cur.append(obj)
            continue
        if len(cur) > 1:
            blocks.append(cur)
        cur = []
    if len(cur) > 1:
        blocks.append(cur)
    moved = 0
    for block in blocks:
        scored = [(relevance(p.text, weights, lib), i, p) for i, p in enumerate(block)]
        new = [p for _, _, p in sorted(scored, key=lambda x: (-x[0], x[1]))]
        if [p._p for p in new] == [p._p for p in block]:
            continue
        parent = block[0]._p.getparent()
        idx = parent.index(block[0]._p)
        for p in block:
            parent.remove(p._p)
        for k, p in enumerate(new):
            parent.insert(idx + k, p._p)
        moved += sum(1 for a, b in zip(block, new) if a._p is not b._p)
        report["bullets_moved_up"].extend(p.text.strip()[:90] for p in new[:1] if p._p is not block[0]._p)
    report["bullet_blocks"] = len(blocks)
    report["bullets_reordered"] = moved


def _split_items(text: str) -> tuple[list[str], str]:
    """Split 'a, b (c, d), e' on top-level separators. Returns (items, separator used)."""
    sep_counts = Counter(m.group(0) for m in re.finditer(r"\s*[,;|•]\s*", text))
    items, buf, depth = [], [], 0
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        if ch in ",;|•" and depth == 0:
            items.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    items.append("".join(buf).strip())
    sep = sep_counts.most_common(1)[0][0] if sep_counts else ", "
    sep = sep.strip() + " " if sep.strip() in ",;" else f" {sep.strip()} "
    return [i for i in items if i], sep


_LABEL = re.compile(r"^(?P<label>[^:|\n]{1,40}?\s*[:|]\s*)(?P<items>.+)$")


def _rewrite_runs(p: Paragraph, label: str, items: list[str], sep: str, bold: set[str]) -> None:
    runs = p.runs
    label_rpr = deepcopy(runs[0]._r.rPr) if runs and runs[0]._r.rPr is not None else None
    item_rpr = deepcopy(runs[-1]._r.rPr) if runs and runs[-1]._r.rPr is not None else None
    for r in runs:
        r._r.getparent().remove(r._r)

    def add(text, rpr, make_bold=False):
        run = p.add_run(text)
        if rpr is not None:
            run._r.insert(0, deepcopy(rpr))
        if make_bold:
            run.bold = True
        return run

    if label:
        add(label, label_rpr)
    for i, it in enumerate(items):
        add(it, item_rpr, it in bold)
        if i < len(items) - 1:
            add(sep, item_rpr)


def _reorder_items_paragraph(p: Paragraph, rank: dict[str, int], lib, bold_on: bool, has_label: bool) -> bool:
    if p._p.find(qn("w:hyperlink")) is not None or not p.text.strip():
        return False
    text = p.text
    label = ""
    if has_label:
        m = _LABEL.match(text)
        if m:
            label, text = m.group("label"), m.group("items")
    items, sep = _split_items(text)
    if len(items) < 2:
        return False
    keyed = []
    for i, it in enumerate(items):
        hits = [rank[n] for n in skills.find(it, lib) if n in rank]
        keyed.append((min(hits) if hits else None, i, it))
    matched_items = [k for k in keyed if k[0] is not None]
    if not matched_items:
        return False
    new = [it for _, _, it in sorted(matched_items)] + [it for r, _, it in keyed if r is None]
    bold = {it for _, _, it in matched_items} if bold_on else set()
    if new == items and not bold:
        return False
    _rewrite_runs(p, label, new, sep, bold)
    return True


def reorder_skills(doc, matched: list[str], lib, bold_on: bool, report) -> None:
    rank = {n: i for i, n in enumerate(matched)}
    changed = 0
    for sec, kind, obj in walk(doc):
        if sec != "skills":
            continue
        if kind == "para":
            changed += _reorder_items_paragraph(obj, rank, lib, bold_on, has_label=True)
        elif kind == "table":
            for row in obj.rows:
                cells = row.cells
                targets = cells[1:] if len(cells) > 1 else cells
                for cell in targets:
                    for p in cell.paragraphs:
                        changed += _reorder_items_paragraph(p, rank, lib, bold_on, has_label=len(cells) == 1)
    report["skill_lines_reordered"] = changed


def add_key_skills_line(doc, matched: list[str], report) -> None:
    if not matched:
        return
    target = None
    for sec, kind, obj in walk(doc):
        if sec == "summary" and kind == "para" and obj.text.strip():
            target = obj
            break
    if target is None:
        report["key_skills_line"] = None
        return
    new_p = deepcopy(target._p)
    for r in new_p.findall(qn("w:r")) + new_p.findall(qn("w:hyperlink")):
        new_p.remove(r)
    target._p.addnext(new_p)
    para = Paragraph(new_p, target._parent)
    label = para.add_run(KEY_SKILLS_LABEL)
    label.bold = True
    line = ", ".join(display_skills(matched)[:8])
    para.add_run(line)
    report["key_skills_line"] = KEY_SKILLS_LABEL + line


# ------------------------------------------------------------------ optional Claude rewording
REWORD_PROMPT = """Rewrite each resume bullet so it uses the job description's wording where it is TRUE to the
original bullet. Strict rules: keep the same facts; do NOT add any technology, tool, skill, number,
metric, employer or claim that is not already in that bullet; keep it one sentence, similar length.
If a bullet can't be improved honestly, return it unchanged.

JOB TITLE: {title}
KEY JD TERMS: {terms}

BULLETS (JSON list):
{bullets}

Return ONLY JSON: {{"bullets": ["...", "..."]}} with the same number of items in the same order.
"""


def bullet_ok(original: str, new: str, lib) -> tuple[bool, str]:
    if not new.strip():
        return False, "empty"
    extra_skills = set(skills.find(new, lib)) - set(skills.find(original, lib))
    if extra_skills:
        return False, "adds " + ", ".join(sorted(extra_skills))
    extra_nums = set(n.strip() for n in _NUM.findall(new)) - set(n.strip() for n in _NUM.findall(original))
    if extra_nums:
        return False, "adds number " + ", ".join(sorted(extra_nums))
    if len(new) > max(60, 1.6 * len(original)):
        return False, "much longer"
    return True, ""


def reword_with_claude(doc, job, matched, lib, settings, report) -> None:
    bullets = [obj for sec, kind, obj in walk(doc)
               if kind == "para" and sec in ("experience", "projects") and obj.text.strip() and is_bullet(obj)][:40]
    if not bullets:
        return
    texts = [b.text.strip() for b in bullets]
    prompt = REWORD_PROMPT.format(title=job["title"], terms=", ".join(matched[:15]),
                                  bullets=json.dumps(texts, ensure_ascii=False))
    out = claude_cli.ask_json(prompt, model=settings.get("claude_model_tailor", "sonnet"),
                              timeout=int(settings.get("claude_timeout_sec", 240)))
    new_texts = out.get("bullets") or []
    if len(new_texts) != len(texts):
        report["reword"] = {"accepted": 0, "rejected": len(texts), "note": "Claude returned a different bullet count"}
        return
    accepted, rejected = 0, []
    for p, old, new in zip(bullets, texts, new_texts):
        new = str(new).strip()
        if new == old:
            continue
        ok, why = bullet_ok(old, new, lib)
        if not ok:
            rejected.append(f"{old[:60]}… ({why})")
            continue
        prefix = re.match(r"^\s*[•\-–*▪◦●‣]\s*", p.text)
        runs = p.runs
        rpr = deepcopy(runs[0]._r.rPr) if runs and runs[0]._r.rPr is not None else None
        for r in runs:
            r._r.getparent().remove(r._r)
        run = p.add_run((prefix.group(0) if prefix else "") + new)
        if rpr is not None:
            run._r.insert(0, rpr)
        accepted += 1
    report["reword"] = {"accepted": accepted, "rejected": len(rejected), "rejected_examples": rejected[:5]}


# ------------------------------------------------------------------ honesty guard
def honesty_check(base_text: str, new_text: str, lib, strict_words: bool) -> tuple[bool, str]:
    extra = set(skills.find(new_text, lib)) - set(skills.find(base_text, lib))
    if extra:
        return False, "new skills appeared: " + ", ".join(sorted(extra))
    nums_new = Counter(n.strip() for n in _NUM.findall(new_text))
    nums_base = Counter(n.strip() for n in _NUM.findall(base_text))
    if nums_new - nums_base:
        return False, "new numbers appeared: " + ", ".join(sorted(nums_new - nums_base))
    if strict_words:
        def words(t):
            t = "\n".join(l for l in t.splitlines() if not l.strip().startswith(KEY_SKILLS_LABEL.strip()))
            return Counter(re.findall(r"\w+", t.lower()))
        if words(new_text) != words(base_text):
            diff = (words(new_text) - words(base_text)) + (words(base_text) - words(new_text))
            return False, "wording changed: " + ", ".join(list(diff)[:8])
    return True, "ok"


# ------------------------------------------------------------------ main entry
_LEGAL = re.compile(r"\b(inc|llc|ltd|limited|corp|corporation|co|company|plc|lp|llp|pvt|private)\b\.?", re.I)


def _short(text: str, max_len: int) -> str:
    """Slug cut at a word boundary (never mid-word)."""
    words, out = slug(text, 200).split("_"), ""
    for w in words:
        if out and len(out) + 1 + len(w) > max_len:
            break
        out = f"{out}_{w}" if out else w
    return out or slug(text, max_len)


def output_name(company: str, title: str, when: date | None = None) -> str:
    """Company_Role_YYYY-MM-DD, e.g. Charles_Schwab_Java_Developer_2026-11-14."""
    when = when or date.today()
    company = _LEGAL.sub(" ", company or "").strip() or "Company"
    return f"{_short(company, 30)}_{_short(title or 'Role', 40)}_{when.isoformat()}"


def file_stem(pattern: str, name: str, company: str, role: str, when: date | None = None) -> str:
    """Fill the user's file-name pattern ({name} {role} {company} {date}) into a safe file name."""
    when = when or date.today()
    values = {"name": _short(name, 40) if name else "", "role": _short(role or "Role", 40),
              "company": _short(_LEGAL.sub(" ", company or "").strip() or "Company", 30), "date": when.isoformat()}
    out = pattern or "{name}_{role}_Resume"
    for k, v in values.items():
        out = out.replace("{" + k + "}", v)
    out = re.sub(r"[^A-Za-z0-9._ -]+", "_", out)          # only characters every OS and email client accepts
    out = re.sub(r"_+", "_", out).strip("_. -")
    return out[:120] or "Resume"


def unique_dir(parent: Path, stem: str) -> Path:
    d, n = parent / stem, 2
    while d.exists():
        d, n = parent / f"{stem}_{n}", n + 1
    d.mkdir(parents=True)
    return d


def unique_path(folder: Path, stem: str, ext: str) -> Path:
    p = folder / f"{stem}{ext}"
    n = 2
    while p.exists():
        p = folder / f"{stem}_{n}{ext}"
        n += 1
    return p


def tailor_docx(base_path: Path, out_path: Path, job: dict, analysis: dict, settings: dict) -> dict:
    """Write the tailored .docx and return the report. Falls back to an unchanged copy if the guard fails."""
    lib = skills.library(settings.get("custom_skills", "") or "")
    base_text = docx_to_text(base_path)
    resume_skills = set(skills.find(base_text, lib))
    matched = [m for m in canonical_matched(analysis, lib) if m in resume_skills]
    weights = _weights(matched)
    report = {"matched_used": matched, "bullets_moved_up": [], "bullet_blocks": 0, "bullets_reordered": 0,
              "skill_lines_reordered": 0, "key_skills_line": None, "reword": None,
              "gaps": list(analysis.get("missing") or []), "guard": "ok", "fallback": False}

    doc = Document(str(base_path))
    reorder_bullets(doc, weights, lib, report)
    reorder_skills(doc, matched, lib, bool(settings.get("tailor_bold_skills", True)), report)
    if settings.get("tailor_key_skills_line", True):
        add_key_skills_line(doc, matched, report)
    reworded = False
    if settings.get("tailor_reword_with_claude") and claude_cli.available():
        try:
            reword_with_claude(doc, job, matched, lib, settings, report)
            reworded = bool(report["reword"] and report["reword"].get("accepted"))
        except Exception as e:  # optional step: never block tailoring
            report["reword"] = {"accepted": 0, "rejected": 0, "note": f"skipped: {e}"[:200]}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))

    ok, why = honesty_check(base_text, docx_to_text(out_path), lib, strict_words=not reworded)
    if not ok:
        shutil.copyfile(base_path, out_path)
        report.update(guard=why, fallback=True)
    return report


def cover_note(job: dict, analysis: dict, base_text: str, settings: dict) -> str:
    """Short, honest cover note: matched skills + the most relevant bullet, quoted from the resume."""
    lib = skills.library(settings.get("custom_skills", "") or "")
    matched = canonical_matched(analysis, lib)
    resume_skills = set(skills.find(base_text, lib))
    matched = display_skills([m for m in matched if m in resume_skills])[:4]
    weights = _weights(matched)
    # sentence-like lines from the work-experience section only (not the summary or skill lists)
    from .resume_insights import _experience_lines
    lines = [l.strip(" •-–*\t") for l in _experience_lines(base_text)
             if len(l.split()) >= 6 and l.count(",") <= 3 and "|" not in l and not re.match(r"^[^:]{1,30}:", l.strip())]
    best = max(lines, key=lambda l: relevance(l, weights, lib), default="") if matched else ""
    first = next((l.strip() for l in base_text.splitlines() if l.strip()), "")
    name = first if (len(first.split()) <= 4 and not re.search(r"[\d@|]", first)) else ""
    if len(matched) > 1:
        skills_phrase = ", ".join(matched[:-1]) + " and " + matched[-1]
    else:
        skills_phrase = matched[0] if matched else "the skills in my resume"
    parts = [
        "Dear Hiring Team,",
        f"I'm applying for the {job.get('title') or 'open'} role at {job.get('company') or 'your company'}. "
        f"My background includes {skills_phrase}, which line up with what this role needs.",
    ]
    if best and relevance(best, weights, lib) > 0:
        parts.append(f"One example from my experience: {best.rstrip('.')}.")
    parts.append("I'd welcome the chance to talk about how I can help your team. Thank you for your time.")
    parts.append("Best regards," + (f"\n{name}" if name else ""))
    return "\n\n".join(parts)


def rename_tailored(conn, job_id: int, new_stem: str) -> dict:
    """Rename a job's tailored .docx / .pdf / cover note (same folder). Returns the new paths."""
    from . import repo

    job = repo.get_job(conn, job_id)
    if not job or not job.get("tailored_docx"):
        raise ValueError("This job has no tailored resume yet.")
    typed = re.sub(r"\.(docx|pdf)$", "", (new_stem or "").strip(), flags=re.I)
    if not typed:
        raise ValueError("Please type a file name.")
    stem = file_stem(typed, "", "", "")
    old_docx = Path(job["tailored_docx"])
    moves = {}
    note_stem = re.sub(r"_?Resume$", "", stem) + "_Cover_Note"
    for col, name in (("tailored_docx", f"{stem}.docx"), ("tailored_pdf", f"{stem}.pdf"),
                      ("cover_note_path", f"{note_stem}.txt")):
        if job.get(col) and Path(job[col]).exists():
            target = old_docx.parent / name
            if target.exists() and target != Path(job[col]):
                raise ValueError(f"{target.name} already exists in this job's folder.")
            moves[col] = (Path(job[col]), target)
    for col, (src, dst) in moves.items():
        src.rename(dst)
    new = {col: str(dst) for col, (_, dst) in moves.items()}
    conn.execute("UPDATE jobs SET tailored_docx = ?, tailored_pdf = ?, cover_note_path = ? WHERE id = ?",
                 (new.get("tailored_docx", job["tailored_docx"]), new.get("tailored_pdf", job.get("tailored_pdf")),
                  new.get("cover_note_path", job.get("cover_note_path")), job_id))
    conn.commit()
    return new


def tailor_job(conn, job_id: int, settings: dict, *, log=print) -> dict:
    """Tailor the resume for one job; write .docx (+ .pdf, + cover note); update the job row."""
    from . import analysis as analysis_mod, pdf, repo

    job = repo.get_job(conn, job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")
    if not job["analyzed_at"]:
        analysis_mod.analyze_job(conn, job_id, log=log)
        job = repo.get_job(conn, job_id)
    resume = repo.get_resume(conn, job["resume_id"]) if job["resume_id"] else repo.resume_for_job(conn, job_id)
    if not resume:
        raise ValueError("Upload a base resume first (Resumes page).")
    base_path = paths.RESUMES / resume["file_name"]
    # one folder per job (Company_Role_Date); the file inside carries the name the employer will see
    folder = unique_dir(paths.TAILORED, output_name(job["company"], job["title"]))
    from .resume_doc import parse as parse_resume
    person = (settings.get("full_name") or "").strip() or parse_resume(base_path).name
    stem = file_stem(settings.get("tailored_file_pattern", ""), person, job["company"], job["title"])
    out_docx = folder / f"{stem}.docx"
    log(f"Tailoring '{resume['name']}' for {job['title']} @ {job['company']}")
    report = tailor_docx(base_path, out_docx, job, job["analysis"] or {}, settings)
    report["base_resume"] = resume["name"]
    log(f"  bullets reordered: {report['bullets_reordered']}, skill lines: {report['skill_lines_reordered']}, "
        f"key-skills line: {'yes' if report['key_skills_line'] else 'no'}, honesty check: {report['guard']}")

    out_pdf = None
    if settings.get("make_pdf", True):
        try:
            out_pdf = out_docx.with_suffix(".pdf")
            report["pdf_method"] = pdf.docx_to_pdf(out_docx, out_pdf, settings.get("browser_channel", "chrome"))
            log(f"  PDF saved ({report['pdf_method']})")
        except Exception as e:
            out_pdf = None
            report["pdf_method"] = None
            report["pdf_error"] = str(e)[:300]
            log(f"  PDF not created: {e}")

    note_path = None
    if settings.get("cover_note_enabled"):
        note = cover_note(job, job["analysis"] or {}, docx_to_text(base_path), settings)
        note_path = out_docx.with_name(out_docx.stem.replace("_Resume", "") + "_Cover_Note.txt")
        note_path.write_text(note, encoding="utf-8")
    else:
        note = None

    repo.save_tailoring(conn, job_id, str(out_docx), str(out_pdf) if out_pdf else None, report,
                        note, str(note_path) if note_path else None)
    return report
