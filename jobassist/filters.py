"""Profile filters applied to every job (same rules for every site)."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .jd_parse import auth_blockers
from .options import POSTED_DAYS
from .textutil import contains_term, parse_iso

_SENIOR = re.compile(r"\b(senior|sr\.?|lead|principal|staff|architect|manager|head|director)\b", re.I)
_ENTRY = re.compile(r"\b(junior|jr\.?|entry|graduate|grad|intern|internship|trainee|fresher|associate)\b", re.I)


def experience_of(title: str) -> str:
    if _SENIOR.search(title or ""):
        return "Senior"
    if _ENTRY.search(title or ""):
        return "Entry"
    return "Mid"


def title_excluded(profile: dict, title: str) -> str | None:
    """Cheap check before opening a job page."""
    for term in profile["exclude"]:
        if contains_term(title, term):
            return f'title has excluded "{term}"'
    return None


def evaluate(profile: dict, job: dict, candidate: dict | None = None) -> tuple[bool, str]:
    """Return (matched, reason). `candidate` = app settings (work authorization, hide toggles)."""
    candidate = candidate or {}
    title = job.get("title", "")

    flags = job.get("auth_flags") or []
    if candidate.get("hide_auth_blocked", True):
        blockers = auth_blockers(flags, candidate.get("work_authorization", ""))
        if blockers:
            return False, "visa: " + ", ".join(b.replace("_", " ") for b in blockers)
    if candidate.get("hide_clearance", True) and "clearance" in flags:
        return False, "needs security clearance"

    max_years = int(profile.get("max_years") or 0)
    yrs = job.get("years_required")
    if max_years and yrs and int(yrs) > max_years:
        return False, f"asks {yrs}+ years (your limit {max_years})"
    text = f"{title}\n{job.get('company', '')}\n{job.get('description', '')}"

    for term in profile["exclude"]:
        if contains_term(text, term):
            return False, f'has excluded "{term}"'

    must = profile["must_include"]
    if must:
        found = [t for t in must if contains_term(text, t)]
        if profile.get("must_include_mode") == "any":
            if not found:
                return False, "none of the must-include terms"
        elif len(found) < len(must):
            missing = [t for t in must if t not in found]
            return False, "missing must-include: " + ", ".join(missing)

    levels = profile["experience_levels"]
    if levels and len(levels) < 3:
        lvl = experience_of(title)
        if lvl not in levels:
            return False, f"looks {lvl}-level"

    modes = profile["work_modes"]
    wm = job.get("work_mode") or ""
    if modes and wm and wm not in modes:
        return False, f"work mode is {wm}"

    posted = parse_iso(job.get("posted_at", ""))
    window = POSTED_DAYS.get(profile.get("posted_within") or "", None)
    if posted and window:
        age_days = (datetime.now(timezone.utc) - posted).total_seconds() / 86400
        slack = max(window * 0.25, 1 / 24)  # timezones and site rounding
        if age_days > window + slack:
            return False, f"posted {age_days:.1f} days ago"

    return True, "matched"
