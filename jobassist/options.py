"""Single source of truth for every choice list the UI shows (served at /api/meta)."""

POSTED_WITHIN = [
    {"value": "1h", "label": "Last 1 hour", "days": 1 / 24},
    {"value": "24h", "label": "Last 24 hours", "days": 1},
    {"value": "3d", "label": "Last 3 days", "days": 3},
    {"value": "7d", "label": "Last 7 days", "days": 7},
    {"value": "30d", "label": "Last 30 days", "days": 30},
]
POSTED_DAYS = {p["value"]: p["days"] for p in POSTED_WITHIN}

JOB_TYPES = ["Full-time", "Contract", "C2C", "Part-time"]
EXPERIENCE_LEVELS = ["Entry", "Mid", "Senior"]
WORK_MODES = ["Remote", "Hybrid", "On-site"]

JOB_STATUSES = ["New", "Tailored", "Ready to review", "Applied", "Skipped", "Manual", "Failed"]

RUN_KINDS = {
    "search": "Search",
    "login": "Log in to sites",
    "analyze": "Analyze jobs",
    "tailor": "Tailor resume",
    "apply": "Apply (review before submit)",
    "tailor_apply": "Tailor & Apply",
    "company_test": "Test company page",
}


def meta() -> dict:
    return {
        "posted_within": POSTED_WITHIN,
        "job_types": JOB_TYPES,
        "experience_levels": EXPERIENCE_LEVELS,
        "work_modes": WORK_MODES,
        "job_statuses": JOB_STATUSES,
        "run_kinds": RUN_KINDS,
    }
