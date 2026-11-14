"""SQLite connection, schema and migrations.

Design notes
- A *job* is fetched once (URL is unique across all runs and sites); its JD is cached.
- A *job_hit* is one profile's verdict on a job (matched or filtered, and why). The same
  job can match several profiles without being fetched again. Stats per keyword/site
  come from job_hits.
- List-valued profile fields are stored as JSON text.
- Schema changes go in MIGRATIONS as a new entry; never edit an applied one.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager

from . import paths
from .settings import DEFAULTS

MIGRATIONS: list[str] = [
    # v1: initial schema
    """
    CREATE TABLE settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    CREATE TABLE sites (
        id         INTEGER PRIMARY KEY,
        key        TEXT NOT NULL UNIQUE,
        name       TEXT NOT NULL,
        kind       TEXT NOT NULL DEFAULT 'builtin',   -- builtin | custom
        search_url TEXT,                              -- custom: template with {keyword} and {location}
        enabled    INTEGER NOT NULL DEFAULT 1,
        notes      TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE resumes (
        id            INTEGER PRIMARY KEY,
        name          TEXT NOT NULL,
        file_name     TEXT NOT NULL,        -- stored under resumes/
        original_name TEXT NOT NULL DEFAULT '',
        text          TEXT NOT NULL DEFAULT '',
        is_default    INTEGER NOT NULL DEFAULT 0,
        uploaded_at   TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE profiles (
        id                INTEGER PRIMARY KEY,
        name              TEXT NOT NULL UNIQUE,
        enabled           INTEGER NOT NULL DEFAULT 1,
        keywords          TEXT NOT NULL DEFAULT '[]',
        must_include      TEXT NOT NULL DEFAULT '[]',
        must_include_mode TEXT NOT NULL DEFAULT 'all',   -- all | any
        exclude           TEXT NOT NULL DEFAULT '[]',
        locations         TEXT NOT NULL DEFAULT '[]',
        work_modes        TEXT NOT NULL DEFAULT '[]',
        posted_within     TEXT NOT NULL DEFAULT '24h',
        job_types         TEXT NOT NULL DEFAULT '[]',
        experience_levels TEXT NOT NULL DEFAULT '[]',
        sites             TEXT NOT NULL DEFAULT '["dice"]',
        resume_id         INTEGER REFERENCES resumes(id) ON DELETE SET NULL,
        min_score         INTEGER NOT NULL DEFAULT 70,
        max_jobs          INTEGER NOT NULL DEFAULT 25,
        created_at        TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE companies (
        id          INTEGER PRIMARY KEY,
        name        TEXT NOT NULL,
        careers_url TEXT NOT NULL UNIQUE,
        enabled     INTEGER NOT NULL DEFAULT 1,
        adapter     TEXT,                   -- module name in adapters/ when custom handling is needed
        notes       TEXT NOT NULL DEFAULT '',
        created_at  TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE runs (
        id               INTEGER PRIMARY KEY,
        kind             TEXT NOT NULL,      -- search | login | analyze | tailor_apply
        profile_id       INTEGER REFERENCES profiles(id) ON DELETE SET NULL,
        job_id           INTEGER,
        trigger          TEXT NOT NULL DEFAULT 'manual',   -- manual | schedule
        uses_browser     INTEGER NOT NULL DEFAULT 1,
        status           TEXT NOT NULL DEFAULT 'queued',   -- queued|running|waiting_user|done|failed|cancelled
        message          TEXT NOT NULL DEFAULT '',
        pid              INTEGER,
        log_file         TEXT,
        cancel_requested INTEGER NOT NULL DEFAULT 0,
        jobs_seen        INTEGER NOT NULL DEFAULT 0,
        jobs_new         INTEGER NOT NULL DEFAULT 0,
        jobs_matched     INTEGER NOT NULL DEFAULT 0,
        started_at       TEXT NOT NULL DEFAULT (datetime('now')),
        finished_at      TEXT
    );

    CREATE TABLE jobs (
        id               INTEGER PRIMARY KEY,
        url              TEXT NOT NULL UNIQUE,     -- normalized; the dedupe key
        site             TEXT NOT NULL,
        external_id      TEXT NOT NULL DEFAULT '',
        title            TEXT NOT NULL DEFAULT '',
        company          TEXT NOT NULL DEFAULT '',
        location         TEXT NOT NULL DEFAULT '',
        work_mode        TEXT NOT NULL DEFAULT '',
        job_type         TEXT NOT NULL DEFAULT '',
        posted_at        TEXT NOT NULL DEFAULT '',   -- ISO when known
        posted_text      TEXT NOT NULL DEFAULT '',   -- as shown on the site ("Today", "3 days ago")
        description      TEXT NOT NULL DEFAULT '',
        status           TEXT NOT NULL DEFAULT 'New',
        status_note      TEXT NOT NULL DEFAULT '',
        resume_id        INTEGER REFERENCES resumes(id) ON DELETE SET NULL,
        match_score      INTEGER,
        matched_keywords TEXT NOT NULL DEFAULT '[]',
        missing_keywords TEXT NOT NULL DEFAULT '[]',   -- the "Gaps" list; never written into a resume
        analysis         TEXT,                         -- full Claude analysis JSON
        analyzed_at      TEXT,
        tailored_docx    TEXT,
        tailored_pdf     TEXT,
        cover_note       TEXT,
        first_run_id     INTEGER,
        first_seen_at    TEXT NOT NULL DEFAULT (datetime('now')),
        last_seen_at     TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX idx_jobs_status ON jobs(status);
    CREATE INDEX idx_jobs_site ON jobs(site);

    CREATE TABLE job_hits (
        job_id     INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
        profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
        run_id     INTEGER,
        keyword    TEXT NOT NULL DEFAULT '',
        location   TEXT NOT NULL DEFAULT '',
        site       TEXT NOT NULL DEFAULT '',
        matched    INTEGER NOT NULL DEFAULT 0,
        reason     TEXT NOT NULL DEFAULT '',
        seen_at    TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (job_id, profile_id)
    );
    CREATE INDEX idx_hits_profile ON job_hits(profile_id, matched);

    CREATE TABLE applications (
        id           INTEGER PRIMARY KEY,
        job_id       INTEGER NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
        applied_at   TEXT NOT NULL DEFAULT (datetime('now')),
        status       TEXT NOT NULL DEFAULT 'Applied',  -- Applied | Interview | Rejected | Offer | No response
        resume_file  TEXT,
        follow_up_on TEXT,
        response_at  TEXT,
        notes        TEXT NOT NULL DEFAULT ''
    );
    """,
    # v2: recruiter signals (visa, years, employer type), cross-board duplicates, company checks
    """
    ALTER TABLE jobs ADD COLUMN years_required INTEGER;
    ALTER TABLE jobs ADD COLUMN auth_flags TEXT NOT NULL DEFAULT '[]';
    ALTER TABLE jobs ADD COLUMN employer_type TEXT NOT NULL DEFAULT '';
    ALTER TABLE jobs ADD COLUMN applicants TEXT NOT NULL DEFAULT '';
    ALTER TABLE jobs ADD COLUMN apply_type TEXT NOT NULL DEFAULT '';     -- easy_apply | external | ''
    ALTER TABLE jobs ADD COLUMN fingerprint TEXT NOT NULL DEFAULT '';
    ALTER TABLE jobs ADD COLUMN duplicate_of INTEGER REFERENCES jobs(id) ON DELETE SET NULL;
    CREATE INDEX idx_jobs_fingerprint ON jobs(fingerprint);
    ALTER TABLE profiles ADD COLUMN max_years INTEGER NOT NULL DEFAULT 0;   -- 0 = no limit
    ALTER TABLE companies ADD COLUMN last_status TEXT NOT NULL DEFAULT '';
    ALTER TABLE companies ADD COLUMN last_checked_at TEXT;
    -- How you sign in to each site / company portal. Passwords are NOT here: they live in
    -- Windows Credential Manager (keyring), only when mode = 'saved'.
    CREATE TABLE logins (
        login_key  TEXT PRIMARY KEY,           -- site key (linkedin, dice, ...) or company_<id>
        mode       TEXT NOT NULL DEFAULT 'manual',   -- manual | saved
        username   TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    UPDATE sites SET enabled = 1, notes = '' WHERE key IN ('linkedin', 'indeed');
    UPDATE sites SET notes = 'India job board' WHERE key = 'naukri';
    UPDATE sites SET notes = 'Uses the Companies list' WHERE key = 'company_pages';
    """,
    # v3: tailored resumes
    """
    ALTER TABLE jobs ADD COLUMN tailor_report TEXT;          -- JSON: what changed, honesty check, pdf method
    ALTER TABLE jobs ADD COLUMN tailored_at TEXT;
    ALTER TABLE jobs ADD COLUMN cover_note_path TEXT;
    """,
    # v4: resume sources and designs; application history
    """
    ALTER TABLE resumes ADD COLUMN source_ext TEXT NOT NULL DEFAULT '.docx';   -- what the user uploaded
    ALTER TABLE resumes ADD COLUMN source_file TEXT;                         -- original upload (pdf/doc)
    ALTER TABLE resumes ADD COLUMN converted_by TEXT NOT NULL DEFAULT '';    -- word | pdf2docx | ''
    ALTER TABLE resumes ADD COLUMN design TEXT NOT NULL DEFAULT '';          -- classic | modern | compact | ''
    ALTER TABLE resumes ADD COLUMN parent_id INTEGER REFERENCES resumes(id) ON DELETE SET NULL;
    ALTER TABLE applications ADD COLUMN channel TEXT NOT NULL DEFAULT '';    -- easy_apply | company_site | email | referral | other
    ALTER TABLE applications ADD COLUMN history TEXT NOT NULL DEFAULT '[]';  -- [{status, at, note}]
    ALTER TABLE applications ADD COLUMN updated_at TEXT;
    """,
    # v5: apply-assist sessions talk to the UI through the run row
    """
    ALTER TABLE runs ADD COLUMN command TEXT;      -- from the UI: submit | done | refill | cancel
    ALTER TABLE runs ADD COLUMN payload TEXT;      -- JSON review card: filled fields, needs-you, final button
    """,
]

BUILTIN_SITES = [
    ("dice", "Dice", 1, ""),
    ("linkedin", "LinkedIn", 1, ""),
    ("indeed", "Indeed", 1, ""),
    ("naukri", "Naukri", 0, "India job board"),
    ("company_pages", "Company career pages", 1, "Uses the Companies list"),
]

SEED_COMPANIES = [
    ("TCS USA", "https://www.tcs.com/careers/united-states"),
]


def connect() -> sqlite3.Connection:
    paths.ensure_dirs()
    conn = sqlite3.connect(paths.DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with session() as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for i, sql in enumerate(MIGRATIONS[version:], start=version + 1):
            conn.executescript(sql)
            conn.execute(f"PRAGMA user_version = {i}")
            if i == 1:
                _seed(conn)
        conn.commit()


def _seed(conn: sqlite3.Connection) -> None:
    for key, name, enabled, notes in BUILTIN_SITES:
        conn.execute(
            "INSERT OR IGNORE INTO sites(key, name, kind, enabled, notes) VALUES(?,?,'builtin',?,?)",
            (key, name, enabled, notes),
        )
    for name, url in SEED_COMPANIES:
        conn.execute("INSERT OR IGNORE INTO companies(name, careers_url) VALUES(?,?)", (name, url))
    for k, v in DEFAULTS.items():
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?,?)", (k, json.dumps(v)))
