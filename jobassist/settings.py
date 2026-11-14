"""App settings. The spec drives both defaults and the Settings page UI."""
from __future__ import annotations

import json

WORK_AUTH_OPTIONS = [
    "F-1 OPT / STEM OPT (will need H-1B later)",
    "H-1B (needs transfer)",
    "Other visa that needs sponsorship",
    "Green card / EAD (no sponsorship needed)",
    "US citizen",
]
NEEDS_SPONSORSHIP = set(WORK_AUTH_OPTIONS[:3])

SPEC: list[dict] = [
    # Candidate (drives visa / experience screening for every profile)
    {"key": "work_authorization", "label": "Your work authorization", "type": "select",
     "options": WORK_AUTH_OPTIONS, "default": WORK_AUTH_OPTIONS[0], "group": "Candidate"},
    {"key": "years_of_experience", "label": "Your years of professional experience (internships count as part)",
     "type": "number", "default": 1, "min": 0, "max": 40, "group": "Candidate"},
    {"key": "full_name", "label": "Your full name (used in tailored resume file names; leave empty to use the name on your resume)",
     "type": "text", "default": "", "group": "Candidate"},
    {"key": "hide_auth_blocked", "label": "Hide jobs that rule out my visa status (no sponsorship, citizens / GC only)",
     "type": "bool", "default": True, "group": "Candidate"},
    {"key": "hide_clearance", "label": "Hide jobs that require a security clearance", "type": "bool",
     "default": True, "group": "Candidate"},
    # Browser & pacing
    {"key": "delay_min_sec", "label": "Min wait between page actions (seconds)", "type": "number",
     "default": 4, "min": 1, "max": 120, "group": "Browser & pacing"},
    {"key": "delay_max_sec", "label": "Max wait between page actions (seconds)", "type": "number",
     "default": 10, "min": 1, "max": 300, "group": "Browser & pacing"},
    {"key": "page_timeout_sec", "label": "Page load timeout (seconds)", "type": "number",
     "default": 45, "min": 10, "max": 180, "group": "Browser & pacing"},
    {"key": "max_pages_per_search", "label": "Result pages per keyword + location", "type": "number",
     "default": 2, "min": 1, "max": 10, "group": "Browser & pacing"},
    {"key": "max_detail_pages_per_run", "label": "Max job pages opened per run (all sites)", "type": "number",
     "default": 60, "min": 5, "max": 500, "group": "Browser & pacing"},
    {"key": "user_wait_minutes", "label": "How long to wait for me to clear a captcha / login (minutes)",
     "type": "number", "default": 10, "min": 1, "max": 60, "group": "Browser & pacing"},
    {"key": "browser_channel", "label": "Browser to drive (your installed Chrome is recommended)",
     "type": "select", "options": ["chrome", "msedge", "chromium"], "default": "chrome", "group": "Browser & pacing"},
    {"key": "headless", "label": "Hide the browser window (captchas and logins need it visible)",
     "type": "bool", "default": False, "group": "Browser & pacing"},
    # Matching
    {"key": "auto_analyze", "label": "Score new matching jobs against my resume after each search run",
     "type": "bool", "default": True, "group": "Matching"},
    {"key": "analysis_engine", "label": "Analysis engine (built-in works offline, no account needed)",
     "type": "select", "options": ["builtin", "claude"], "default": "builtin", "group": "Matching"},
    {"key": "custom_skills", "label": "Extra skills to recognise, one per line. Optional synonyms after a colon, "
     "e.g.  Guidewire: guidewire policycenter, gw", "type": "textarea", "default": "", "group": "Matching"},
    # Tailoring
    {"key": "auto_tailor", "label": "Tailor my resume automatically for jobs scoring at least the profile's minimum",
     "type": "bool", "default": True, "group": "Tailored resumes"},
    {"key": "tailor_bold_skills", "label": "Bold the skills this job asks for in my Skills section", "type": "bool",
     "default": True, "group": "Tailored resumes"},
    {"key": "tailor_key_skills_line", "label": "Add a 'Key skills for this role' line under my summary (only skills already in my resume)",
     "type": "bool", "default": True, "group": "Tailored resumes"},
    {"key": "tailored_file_pattern", "label": "File name for tailored resumes. Use {name} {role} {company} {date}",
     "type": "text", "default": "{name}_{role}_Resume", "group": "Tailored resumes"},
    {"key": "make_pdf", "label": "Also save a PDF copy", "type": "bool", "default": True, "group": "Tailored resumes"},
    {"key": "cover_note_enabled", "label": "Write a short cover note per job", "type": "bool",
     "default": False, "group": "Tailored resumes"},
    {"key": "tailor_reword_with_claude", "label": "Let Claude reword bullets to mirror the job's wording (checked: no new skills or numbers)",
     "type": "bool", "default": False, "group": "Optional: Claude CLI"},
    # Optional Claude
    {"key": "claude_model_analysis", "label": "Claude model for JD analysis (only if engine = claude)",
     "type": "select", "options": ["haiku", "sonnet", "opus"], "default": "haiku", "group": "Optional: Claude CLI"},
    {"key": "claude_model_tailor", "label": "Claude model for resume rewording (only if engine = claude)",
     "type": "select", "options": ["haiku", "sonnet", "opus"], "default": "sonnet",
     "group": "Optional: Claude CLI"},
    {"key": "claude_timeout_sec", "label": "Claude call timeout (seconds)", "type": "number",
     "default": 240, "min": 30, "max": 900, "group": "Optional: Claude CLI"},
    # Applying
    {"key": "daily_apply_cap", "label": "Max applications per day", "type": "number",
     "default": 15, "min": 1, "max": 100, "group": "Applying"},
    {"key": "apply_wait_minutes", "label": "Keep a filled application open for review for (minutes)", "type": "number",
     "default": 30, "min": 5, "max": 240, "group": "Applying"},
    {"key": "follow_up_days", "label": "Follow-up reminder after (days)", "type": "number",
     "default": 7, "min": 1, "max": 60, "group": "Applying"},
    # Schedule
    {"key": "schedule_time", "label": "Daily run time (24h, HH:MM)", "type": "time",
     "default": "08:00", "group": "Schedule & notifications"},
    {"key": "notify_on_finish", "label": "Desktop notification when a run finishes", "type": "bool",
     "default": True, "group": "Schedule & notifications"},
]

DEFAULTS = {s["key"]: s["default"] for s in SPEC}
_BY_KEY = {s["key"]: s for s in SPEC}


def coerce(key: str, value):
    spec = _BY_KEY.get(key)
    if spec is None:
        raise KeyError(f"Unknown setting: {key}")
    t = spec["type"]
    if t == "number":
        v = float(value)
        v = max(spec.get("min", v), min(spec.get("max", v), v))
        return int(v) if float(v).is_integer() else v
    if t == "bool":
        return bool(value)
    if t == "select":
        if value not in spec["options"]:
            raise ValueError(f"{key} must be one of {spec['options']}")
        return value
    if t in ("text", "textarea"):
        return str(value or "")[:20000]
    if t == "time":
        hh, mm = str(value).split(":")
        if not (0 <= int(hh) < 24 and 0 <= int(mm) < 60):
            raise ValueError("time must be HH:MM")
        return f"{int(hh):02d}:{int(mm):02d}"
    return value


def load(conn) -> dict:
    out = dict(DEFAULTS)
    for row in conn.execute("SELECT key, value FROM settings"):
        if row["key"] in _BY_KEY:
            out[row["key"]] = json.loads(row["value"])
    if out["delay_max_sec"] < out["delay_min_sec"]:
        out["delay_max_sec"] = out["delay_min_sec"]
    return out


def save(conn, values: dict) -> dict:
    for k, v in values.items():
        v = coerce(k, v)
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (k, json.dumps(v)),
        )
    conn.commit()
    return load(conn)
