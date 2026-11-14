"""Resume insights and search suggestions (built-in, offline).

- top_skills():          skills the resume shows, strongest first
- estimate_experience(): years of work experience from the resume's date ranges
                         (education dates ignored, overlapping jobs not double-counted)
- score_roles():         which roles (data/roles.yaml) the resume fits, with confidence
- suggest():             search titles, exclude words, must-include and profile defaults to accept/reject

Optional: when Settings > Analysis engine = claude and Claude Code is installed, Claude adds a few
extra title ideas (marked as such). Everything else stays deterministic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

from . import claude_cli, skills

ROLES_FILE = Path(__file__).parent / "data" / "roles.yaml"


# ------------------------------------------------------------------ roles
@dataclass(frozen=True)
class Role:
    name: str
    titles: tuple[str, ...]
    entry: tuple[str, ...]
    core: tuple[str, ...]
    signals: tuple[tuple[str, float], ...]


@lru_cache(maxsize=1)
def roles() -> tuple[Role, ...]:
    data = yaml.safe_load(ROLES_FILE.read_text(encoding="utf-8")) or {}
    return tuple(
        Role(name, tuple(r.get("titles") or []), tuple(r.get("entry") or []), tuple(r.get("core") or []),
             tuple((k, float(v)) for k, v in (r.get("signals") or {}).items()))
        for name, r in data.items())


GENERAL = "General Software Engineer"


def score_roles(found: dict[str, int]) -> list[dict]:
    """Confidence 0-1 per role = share of the role's signal weight the resume shows (needs a core hit)."""
    out = []
    for r in roles():
        if r.core and not any(c in found for c in r.core):
            continue
        total = sum(w for _, w in r.signals) or 1.0
        hit = [(k, w) for k, w in r.signals if k in found]
        conf = sum(w for _, w in hit) / total
        out.append({"name": r.name, "confidence": round(conf, 2),
                    "matched": [k for k, _ in sorted(hit, key=lambda x: -x[1])]})
    return sorted(out, key=lambda x: (x["name"] == GENERAL, -x["confidence"]))


# ------------------------------------------------------------------ skills
def top_skills(text: str, custom_skills: str = "", limit: int = 25) -> list[dict]:
    lib = skills.library(custom_skills or "")
    meta = skills.by_name(lib)
    found = dict(skills.find(text, lib))
    # "Spring Boot" mentions also match "Spring"; count the generic skill only for its own mentions.
    for general in list(found):
        for specific, n in list(found.items()):
            if specific != general and specific.lower().startswith(general.lower() + " "):
                found[general] = max(0, found[general] - n)
    found = {k: v for k, v in found.items() if v > 0}
    ranked = sorted(found.items(), key=lambda kv: (-(kv[1] * meta[kv[0]].weight), kv[0]))
    return [{"name": n, "category": meta[n].category, "count": c} for n, c in ranked[:limit]]


# ------------------------------------------------------------------ experience
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_END = r"(present|current|now|till date|to date|today|ongoing)"
_DASH = r"\s*(?:-|–|—|to|until)\s*"
_PATTERNS = [
    re.compile(rf"(?P<sm>{_MON})\s*,?\s*(?P<sy>(?:19|20)\d{{2}}){_DASH}(?:(?P<em>{_MON})\s*,?\s*(?P<ey>(?:19|20)\d{{2}})|(?P<now>{_END}))", re.I),
    re.compile(rf"(?P<smn>\d{{1,2}})\s*/\s*(?P<sy>(?:19|20)\d{{2}}){_DASH}(?:(?P<emn>\d{{1,2}})\s*/\s*(?P<ey>(?:19|20)\d{{2}})|(?P<now>{_END}))", re.I),
    re.compile(rf"(?<![\d/])(?P<sy>(?:19|20)\d{{2}}){_DASH}(?:(?P<ey>(?:19|20)\d{{2}})|(?P<now>{_END}))(?![\d/])", re.I),
]
_MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_EXP_HEAD = re.compile(r"^\W*(?:professional |work |relevant |industry |technical )?(?:experience|employment(?: history)?|"
                       r"work history|career history|internships?)\b", re.I)
_OTHER_HEAD = re.compile(r"^\W*(?:education|academic|academics|projects?|academic projects|personal projects|skills|"
                         r"technical skills|certifications?|summary|professional summary|profile|objective|publications|"
                         r"awards|achievements|honors|volunteer\w*|coursework|languages)\b", re.I)
# Degree words (any case) + degree abbreviations only as written on resumes (B.E., BS, MS, B.Tech...),
# so ordinary words like "be" or "ms" in a sentence don't knock out work-history lines.
_EDU_LINE = re.compile(r"(?i:\b(?:university|college|institute|school|bachelor'?s?|master'?s?|degree|gpa|cgpa|"
                       r"graduat\w+|coursework|b\.?\s?tech|m\.?\s?tech|ph\.?d)\b)|"
                       r"\b(?:B\.E\.|B\.S\.|M\.S\.|BE|BS|MS|MBA|BSc|MSc|MCA|BCA)\b")


def _month(token: str | None, numeric: str | None, default: int) -> int:
    if numeric:
        n = int(numeric)
        return n if 1 <= n <= 12 else default
    if token:
        return _MONTHS.get(token[:3].lower(), default)
    return default


def _experience_lines(text: str) -> list[str]:
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    has_exp_head = any(len(l) <= 50 and _EXP_HEAD.search(l) for l in lines)
    out, in_exp = [], not has_exp_head
    for i, line in enumerate(lines):
        short = len(line) <= 50
        if short and _EXP_HEAD.search(line):
            in_exp = True
            continue
        if short and _OTHER_HEAD.search(line):
            in_exp = False
            continue
        context = line + " " + (lines[i - 1] if i else "")
        if in_exp and not _EDU_LINE.search(context):
            out.append(line)
    return out


def estimate_experience(text: str, today: date | None = None) -> dict:
    """{'years': float|None, 'ranges': [{'from','to','line'}], 'includes_internships': bool}"""
    today = today or date.today()
    now_idx = today.year * 12 + today.month - 1
    spans, ranges, intern = [], [], False
    lines = _experience_lines(text)
    for i, line in enumerate(lines):
        taken: list[tuple[int, int]] = []
        for rx in _PATTERNS:
            for m in rx.finditer(line):
                if any(a < m.end() and m.start() < b for a, b in taken):
                    continue
                taken.append((m.start(), m.end()))
                g = m.groupdict()
                sy = int(g["sy"])
                sm = _month(g.get("sm"), g.get("smn"), 1)
                start = sy * 12 + sm - 1
                if g.get("now"):
                    end = now_idx
                else:
                    ey = int(g["ey"])
                    end = ey * 12 + _month(g.get("em"), g.get("emn"), 12 if not (g.get("em") or g.get("emn")) else 1) - 1
                end = min(end, now_idx)
                if end < start or end - start > 12 * 45:
                    continue
                spans.append((start, end))
                ranges.append({"from": f"{start // 12}-{start % 12 + 1:02d}", "to": f"{end // 12}-{end % 12 + 1:02d}",
                               "line": line[:120]})
                around = " ".join(lines[max(0, i - 1): i + 2]).lower()
                intern = intern or "intern" in around
    if not spans:
        return {"years": None, "ranges": [], "includes_internships": False}
    spans.sort()
    months, cur_s, cur_e = 0, *spans[0]
    for s, e in spans[1:]:
        if s <= cur_e + 1:
            cur_e = max(cur_e, e)
        else:
            months += cur_e - cur_s + 1
            cur_s, cur_e = s, e
    months += cur_e - cur_s + 1
    return {"years": round(months / 12, 1), "ranges": ranges, "includes_internships": intern}


# ------------------------------------------------------------------ suggestions
SENIOR_WORDS = ["Senior", "Sr.", "Lead", "Principal", "Staff", "Architect", "Manager"]
MID_EXCLUDE = ["Principal", "Architect", "Manager", "Director"]


def _item(value: str, reason: str, selected: bool, source: str = "builtin") -> dict:
    return {"value": value, "reason": reason, "selected": selected, "source": source}


def suggest(resume_text: str, settings: dict, profile: dict | None = None) -> dict:
    custom = settings.get("custom_skills", "") or ""
    found = skills.find(resume_text, skills.library(custom))
    exp = estimate_experience(resume_text)
    years = float(settings.get("years_of_experience") or 0)
    if exp["years"] is not None and not settings.get("years_of_experience"):
        years = exp["years"]
    new_grad = years <= 2

    have = {k.lower() for k in (profile or {}).get("keywords", [])}
    have_ex = {k.lower() for k in (profile or {}).get("exclude", [])}

    ranked = score_roles(found)
    specific = [r for r in ranked if r["name"] != GENERAL and r["confidence"] >= 0.3][:4]
    general = next((r for r in ranked if r["name"] == GENERAL), None)
    by_name = {r.name: r for r in roles()}

    keywords, seen = [], set()

    def add_kw(title: str, reason: str, selected: bool):
        key = title.lower()
        if key in seen or key in have:
            return
        seen.add(key)
        keywords.append(_item(title, reason, selected))

    # Pre-ticked picks follow recruiter practice: a few focused titles, best role first (max 6 ticked).
    for rank, r in enumerate(specific):
        role = by_name[r["name"]]
        why = f"{r['name']}: your resume shows " + ", ".join(r["matched"][:4])
        n_main = 2 if rank == 0 else 1 if rank == 1 else 0
        for i, t in enumerate(role.titles[:3]):
            add_kw(t, why, i < n_main)
        if new_grad:
            for i, t in enumerate(role.entry[:2]):
                add_kw(t, why + " (entry-level title)", rank == 0 and i == 0)
    if general:
        role = by_name[GENERAL]
        why = "General software roles: you have " + ", ".join(general["matched"][:3])
        for i, t in enumerate(list(role.entry[:4] if new_grad else ()) + list(role.titles[:2])):
            add_kw(t, why, new_grad and i < 2 or (not specific and i < 2))
    ticked = 0
    for k in keywords:  # hard cap on pre-ticked titles
        if k["selected"]:
            ticked += 1
            k["selected"] = ticked <= 6

    exclude = []
    words = SENIOR_WORDS if new_grad else MID_EXCLUDE if years <= 6 else []
    for w in words:
        if w.lower() not in have_ex:
            exclude.append(_item(w, f"Senior titles rarely fit {years:g} year(s) of experience", True))

    must = []
    if specific:
        core = [c for c in by_name[specific[0]["name"]].core if c in found]
        if core:
            must.append(_item(core[0], f"Only show jobs that mention {core[0]} (your strongest skill for this role)", False))

    extra_source = None
    if settings.get("analysis_engine") == "claude" and claude_cli.available():
        try:
            ideas = _claude_titles(resume_text, settings, [k["value"] for k in keywords])
            for t in ideas:
                if t.lower() not in seen and t.lower() not in have:
                    seen.add(t.lower())
                    keywords.append(_item(t, "Extra idea from Claude", False, "claude"))
            extra_source = "claude"
        except Exception:
            extra_source = None

    levels = ["Entry", "Mid"] if new_grad else ["Mid"] if years <= 6 else ["Mid", "Senior"]
    top_role = specific[0]["name"] if specific else (GENERAL if general else "My search")
    return {
        "engine": "builtin" + ("+claude" if extra_source else ""),
        "skills": top_skills(resume_text, custom),
        "experience": {**exp, "settings_years": settings.get("years_of_experience")},
        "roles": ranked[:6],
        "suggestions": {"keywords": keywords, "exclude": exclude, "must_include": must},
        "profile_defaults": {
            "name": top_role.replace(" / ", " ").replace("General ", ""),
            "max_years": max(2, int(round(years)) + 2),
            "experience_levels": levels,
        },
    }


def _claude_titles(resume_text: str, settings: dict, already: list[str]) -> list[str]:
    prompt = (
        "Suggest up to 6 job titles this candidate should search for on US job boards, based ONLY on skills "
        "the resume clearly shows. Prefer titles recruiters actually post. Candidate years of experience: "
        f"{settings.get('years_of_experience')}. Skip these (already suggested): {', '.join(already)}.\n"
        'Return ONLY JSON: {"titles": ["..."]}\n\nRESUME:\n' + resume_text[:12000])
    r = claude_cli.ask_json(prompt, model=settings.get("claude_model_analysis", "haiku"),
                            timeout=int(settings.get("claude_timeout_sec", 240)))
    return [str(t).strip() for t in (r.get("titles") or []) if str(t).strip()][:6]
