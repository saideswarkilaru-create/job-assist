"""Every on-disk location the app uses. Nothing else should build paths by hand."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATA = ROOT / "data"
DB_PATH = DATA / "jobassist.db"
CLAUDE_WORKDIR = DATA / "claude-work"   # empty folder so `claude -p` loads no project context

RESUMES = ROOT / "resumes"              # uploaded base resumes (.docx)
TAILORED = ROOT / "tailored"            # Company_Role_Date.docx / .pdf (Phase 4)
BROWSER_PROFILE = ROOT / "browser-profile"  # persistent Chromium profile (your logins live here)
LOGS = ROOT / "logs"
ADAPTERS = ROOT / "adapters"            # per-company custom scrapers (Phase 2)
CONFIG = ROOT / "config"
PROFILE_YAML = CONFIG / "profile.yaml"  # your applicant details for apply-assist (Phase 5)

WEB_DIST = ROOT / "web" / "dist" / "web" / "browser"  # built Angular app


def ensure_dirs() -> None:
    for d in (DATA, CLAUDE_WORKDIR, RESUMES, TAILORED, BROWSER_PROFILE, LOGS, ADAPTERS, CONFIG):
        d.mkdir(parents=True, exist_ok=True)
