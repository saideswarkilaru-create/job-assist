"""Read schema.org JobPosting JSON-LD from a job page. Many job boards and career sites
publish it for Google Jobs, so this is the most stable source of title / company / JD / date."""
from __future__ import annotations

import json

from ..textutil import html_to_text

EMPLOYMENT_TYPES = {
    "FULL_TIME": "Full-time", "FULLTIME": "Full-time",
    "PART_TIME": "Part-time", "PARTTIME": "Part-time",
    "CONTRACTOR": "Contract", "CONTRACT": "Contract", "TEMPORARY": "Contract",
    "INTERN": "Part-time",
}


def _find_posting(obj):
    if isinstance(obj, list):
        for o in obj:
            r = _find_posting(o)
            if r:
                return r
    elif isinstance(obj, dict):
        t = obj.get("@type")
        if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
            return obj
        if "@graph" in obj:
            return _find_posting(obj["@graph"])
    return None


def read_job_posting(page) -> dict | None:
    try:
        blobs = page.eval_on_selector_all('script[type="application/ld+json"]', "els => els.map(e => e.textContent)")
    except Exception:
        return None
    for blob in blobs:
        try:
            posting = _find_posting(json.loads(blob))
        except (json.JSONDecodeError, TypeError):
            continue
        if posting:
            return posting
    return None


def _location(posting: dict) -> str:
    locs = posting.get("jobLocation") or []
    if isinstance(locs, dict):
        locs = [locs]
    out = []
    for loc in locs:
        a = (loc or {}).get("address") or {}
        if isinstance(a, str):
            out.append(a)
            continue
        parts = [a.get("addressLocality"), a.get("addressRegion"), a.get("addressCountry")]
        country = parts[2]
        if isinstance(country, dict):
            parts[2] = country.get("name")
        s = ", ".join(p for p in parts if p)
        if s and s not in out:
            out.append(s)
    return "; ".join(out[:3])


def posting_fields(posting: dict) -> dict:
    org = posting.get("hiringOrganization") or {}
    emp = posting.get("employmentType") or ""
    if isinstance(emp, list):
        emp = emp[0] if emp else ""
    remote = str(posting.get("jobLocationType") or "").upper() == "TELECOMMUTE"
    ident = posting.get("identifier") or {}
    return {
        "title": (posting.get("title") or "").strip(),
        "company": (org.get("name") if isinstance(org, dict) else str(org)) or "",
        "location": _location(posting) or ("Remote" if remote else ""),
        "work_mode": "Remote" if remote else "",
        "job_type": EMPLOYMENT_TYPES.get(str(emp).upper().replace("-", "_"), ""),
        "posted_at": posting.get("datePosted") or "",
        "description": html_to_text(posting.get("description") or ""),
        "external_id": str(ident.get("value", "")) if isinstance(ident, dict) else "",
    }
