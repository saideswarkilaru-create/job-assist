"""Your applicant details (config/profile.yaml), edited on the My details page.

Used only to fill application forms on your computer. Never sent anywhere else, never contains
passwords. Sensitive identifiers (SSN, date of birth, bank details) are deliberately NOT supported:
forms that ask for them get flagged for you to fill by hand.
"""
from __future__ import annotations

import yaml

from . import paths
from .settings import NEEDS_SPONSORSHIP

DECLINE = "Decline to answer"

# key, label, type, group, options/help. The UI renders this list; the form filler reads the values.
SPEC: list[dict] = [
    {"key": "first_name", "label": "First name", "group": "Contact"},
    {"key": "last_name", "label": "Last name", "group": "Contact"},
    {"key": "preferred_name", "label": "Preferred name (optional)", "group": "Contact"},
    {"key": "email", "label": "Email", "group": "Contact"},
    {"key": "phone", "label": "Phone", "group": "Contact", "help": "e.g. +1 469 555 0100"},
    {"key": "address", "label": "Street address (optional)", "group": "Contact"},
    {"key": "city", "label": "City", "group": "Contact"},
    {"key": "state", "label": "State", "group": "Contact", "help": "e.g. Texas or TX"},
    {"key": "zip", "label": "ZIP code", "group": "Contact"},
    {"key": "country", "label": "Country", "group": "Contact"},
    {"key": "linkedin_url", "label": "LinkedIn URL", "group": "Links"},
    {"key": "github_url", "label": "GitHub URL", "group": "Links"},
    {"key": "portfolio_url", "label": "Portfolio / website", "group": "Links"},
    {"key": "current_title", "label": "Current or most recent job title", "group": "Work"},
    {"key": "current_company", "label": "Current or most recent company", "group": "Work"},
    {"key": "notice_period", "label": "Notice period / when you can start", "group": "Work", "help": "e.g. 2 weeks, Immediately"},
    {"key": "expected_salary", "label": "Expected salary (leave empty to answer yourself)", "group": "Work"},
    {"key": "willing_to_relocate", "label": "Willing to relocate", "type": "select", "options": ["Yes", "No", ""], "group": "Work"},
    {"key": "school", "label": "University (highest degree)", "group": "Education"},
    {"key": "degree", "label": "Degree", "group": "Education", "help": "e.g. Master of Science"},
    {"key": "major", "label": "Field of study", "group": "Education", "help": "e.g. Computer Science"},
    {"key": "graduation_date", "label": "Graduation (month year)", "group": "Education", "help": "e.g. May 2024"},
    {"key": "gpa", "label": "GPA (optional)", "group": "Education"},
    {"key": "authorized_to_work", "label": "Legally authorized to work in the US now?", "type": "select",
     "options": ["Yes", "No"], "group": "Work authorization",
     "help": "F-1 OPT / STEM OPT, H-1B, green card and citizens are all authorized now."},
    {"key": "requires_sponsorship", "label": "Will you need visa sponsorship now or in the future?", "type": "select",
     "options": ["Yes", "No"], "group": "Work authorization", "help": "OPT / STEM OPT students usually answer Yes (for H-1B later)."},
    {"key": "gender", "label": "Gender (voluntary)", "type": "select", "options": [DECLINE, "Male", "Female", "Non-binary"],
     "group": "Voluntary self-identification (US EEO)"},
    {"key": "race", "label": "Race / ethnicity (voluntary)", "type": "select",
     "options": [DECLINE, "Asian", "Black or African American", "Hispanic or Latino", "White",
                 "Native Hawaiian or Other Pacific Islander", "American Indian or Alaska Native", "Two or More Races"],
     "group": "Voluntary self-identification (US EEO)"},
    {"key": "veteran", "label": "Protected veteran (voluntary)", "type": "select",
     "options": [DECLINE, "I am not a protected veteran", "I identify as a protected veteran"],
     "group": "Voluntary self-identification (US EEO)"},
    {"key": "disability", "label": "Disability (voluntary)", "type": "select",
     "options": [DECLINE, "No, I don't have a disability", "Yes, I have a disability"],
     "group": "Voluntary self-identification (US EEO)"},
]

DEFAULTS = {s["key"]: "" for s in SPEC} | {"country": "United States", "authorized_to_work": "Yes",
                                            "gender": DECLINE, "race": DECLINE, "veteran": DECLINE, "disability": DECLINE}


def _path():
    return paths.CONFIG / "profile.yaml"


def load(settings: dict | None = None) -> dict:
    data = {}
    try:
        data = yaml.safe_load(_path().read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        pass
    out = dict(DEFAULTS)
    for k, v in data.items():
        if isinstance(v, (list, dict)):
            out[k] = v
        elif v not in (None, ""):          # an empty saved value never wipes a sensible default
            out[k] = str(v)
    if not out.get("requires_sponsorship") and settings:
        out["requires_sponsorship"] = "Yes" if settings.get("work_authorization") in NEEDS_SPONSORSHIP else "No"
    out.setdefault("answers", [])
    if not isinstance(out["answers"], list):
        out["answers"] = []
    return out


def save(values: dict) -> dict:
    """Save the given fields; fields not sent keep their current value."""
    current = load()
    keys = [s["key"] for s in SPEC]
    clean = {k: str((values[k] if k in values else current.get(k, "")) or "").strip()[:300] for k in keys}
    answers = []
    for a in (values["answers"] if "answers" in values else current.get("answers")) or []:
        q, ans = str(a.get("question", "")).strip()[:200], str(a.get("answer", "")).strip()[:1000]
        if q and ans:
            answers.append({"question": q, "answer": ans})
    clean["answers"] = answers
    paths.ensure_dirs()
    header = "# Your applicant details for Job Assist (edit on the My details page). Never put passwords here.\n"
    _path().write_text(header + yaml.safe_dump(clean, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return load()


def full_name(a: dict) -> str:
    return " ".join(x for x in (a.get("first_name"), a.get("last_name")) if x).strip()


def missing_basics(a: dict) -> list[str]:
    need = [("first_name", "first name"), ("last_name", "last name"), ("email", "email"), ("phone", "phone")]
    return [label for k, label in need if not a.get(k)]
