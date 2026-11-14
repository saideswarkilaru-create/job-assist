"""All SQL lives here. API routes and the runner call these functions; nothing else writes SQL."""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

PROFILE_LIST_FIELDS = (
    "keywords", "must_include", "exclude", "locations", "work_modes",
    "job_types", "experience_levels", "sites",
)
PROFILE_FIELDS = PROFILE_LIST_FIELDS + (
    "name", "enabled", "must_include_mode", "posted_within", "resume_id", "min_score", "max_jobs", "max_years",
)
JOB_JSON_FIELDS = ("matched_keywords", "missing_keywords", "analysis", "auth_flags", "tailor_report")


def _row(r: sqlite3.Row | None) -> dict | None:
    return dict(r) if r is not None else None


def _clean_list(values: Any) -> list[str]:
    """Trim, drop empties, dedupe case-insensitively, keep order."""
    out, seen = [], set()
    for v in values or []:
        s = re.sub(r"\s+", " ", str(v)).strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out


# ---------------------------------------------------------------- profiles
def _profile_out(r: sqlite3.Row) -> dict:
    d = dict(r)
    for f in PROFILE_LIST_FIELDS:
        d[f] = json.loads(d[f] or "[]")
    d["enabled"] = bool(d["enabled"])
    return d


def list_profiles(conn) -> list[dict]:
    rows = conn.execute("""
        SELECT p.*,
          (SELECT COUNT(*) FROM job_hits h WHERE h.profile_id = p.id AND h.matched = 1) AS jobs_matched,
          (SELECT MAX(r.started_at) FROM runs r WHERE r.profile_id = p.id AND r.kind = 'search') AS last_run_at
        FROM profiles p ORDER BY p.name COLLATE NOCASE
    """).fetchall()
    return [_profile_out(r) for r in rows]


def get_profile(conn, pid: int) -> dict | None:
    r = conn.execute("SELECT * FROM profiles WHERE id = ?", (pid,)).fetchone()
    return _profile_out(r) if r else None


def _profile_values(data: dict) -> dict:
    vals = {}
    for f in PROFILE_FIELDS:
        if f not in data:
            continue
        v = data[f]
        if f in PROFILE_LIST_FIELDS:
            v = json.dumps(_clean_list(v))
        elif f == "enabled":
            v = 1 if v else 0
        elif f == "name":
            v = str(v).strip()
            if not v:
                raise ValueError("Profile name is required")
        elif f in ("min_score", "max_jobs", "max_years"):
            v = int(v)
        vals[f] = v
    return vals


def create_profile(conn, data: dict) -> dict:
    vals = _profile_values(data)
    if "resume_id" not in vals or vals["resume_id"] is None:
        d = default_resume(conn)
        vals["resume_id"] = d["id"] if d else None
    cols = ", ".join(vals)
    cur = conn.execute(f"INSERT INTO profiles({cols}) VALUES({', '.join('?' * len(vals))})", tuple(vals.values()))
    conn.commit()
    return get_profile(conn, cur.lastrowid)


def update_profile(conn, pid: int, data: dict) -> dict | None:
    vals = _profile_values(data)
    if vals:
        sets = ", ".join(f"{k} = ?" for k in vals)
        conn.execute(f"UPDATE profiles SET {sets}, updated_at = datetime('now') WHERE id = ?",
                     (*vals.values(), pid))
        conn.commit()
    return get_profile(conn, pid)


def duplicate_profile(conn, pid: int) -> dict | None:
    p = get_profile(conn, pid)
    if not p:
        return None
    base, n = f"{p['name']} (copy)", 2
    name = base
    while conn.execute("SELECT 1 FROM profiles WHERE name = ?", (name,)).fetchone():
        name, n = f"{base} {n}", n + 1
    data = {k: p[k] for k in PROFILE_FIELDS if k in p}
    data.update(name=name, enabled=False)
    return create_profile(conn, data)


def delete_profile(conn, pid: int) -> None:
    conn.execute("DELETE FROM profiles WHERE id = ?", (pid,))
    conn.commit()


# ---------------------------------------------------------------- resumes
def list_resumes(conn) -> list[dict]:
    rows = conn.execute("""
        SELECT id, name, file_name, original_name, is_default, uploaded_at, length(text) AS text_chars,
          source_ext, converted_by, design, parent_id,
          (SELECT COUNT(*) FROM profiles p WHERE p.resume_id = resumes.id) AS used_by
        FROM resumes ORDER BY is_default DESC, name COLLATE NOCASE
    """).fetchall()
    return [{**dict(r), "is_default": bool(r["is_default"])} for r in rows]


def get_resume(conn, rid: int) -> dict | None:
    return _row(conn.execute("SELECT * FROM resumes WHERE id = ?", (rid,)).fetchone())


def default_resume(conn) -> dict | None:
    return _row(conn.execute(
        "SELECT * FROM resumes ORDER BY is_default DESC, id LIMIT 1").fetchone())


def create_resume(conn, name: str, file_name: str, original_name: str, text: str, *, source_ext: str = ".docx",
                  source_file: str | None = None, converted_by: str = "", design: str = "",
                  parent_id: int | None = None) -> dict:
    first = conn.execute("SELECT COUNT(*) FROM resumes").fetchone()[0] == 0
    cur = conn.execute(
        "INSERT INTO resumes(name, file_name, original_name, text, is_default, source_ext, source_file, converted_by, "
        "design, parent_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (name, file_name, original_name, text, 1 if first else 0, source_ext, source_file, converted_by, design, parent_id))
    conn.commit()
    return get_resume(conn, cur.lastrowid)


def rename_resume(conn, rid: int, name: str) -> None:
    conn.execute("UPDATE resumes SET name = ? WHERE id = ?", (name.strip(), rid))
    conn.commit()


def set_default_resume(conn, rid: int) -> None:
    conn.execute("UPDATE resumes SET is_default = CASE WHEN id = ? THEN 1 ELSE 0 END", (rid,))
    conn.commit()


def delete_resume(conn, rid: int) -> dict | None:
    r = get_resume(conn, rid)
    if not r:
        return None
    conn.execute("DELETE FROM resumes WHERE id = ?", (rid,))
    if r["is_default"]:
        conn.execute("UPDATE resumes SET is_default = 1 WHERE id = (SELECT MIN(id) FROM resumes)")
    conn.commit()
    return r


# ---------------------------------------------------------------- sites & companies
def list_sites(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM sites ORDER BY kind, id").fetchall()
    return [{**dict(r), "enabled": bool(r["enabled"])} for r in rows]


def get_site(conn, key: str) -> dict | None:
    r = conn.execute("SELECT * FROM sites WHERE key = ?", (key,)).fetchone()
    return {**dict(r), "enabled": bool(r["enabled"])} if r else None


def create_site(conn, name: str, search_url: str, notes: str = "") -> dict:
    key = "custom_" + (re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "site")
    base, n = key, 2
    while conn.execute("SELECT 1 FROM sites WHERE key = ?", (key,)).fetchone():
        key, n = f"{base}_{n}", n + 1
    conn.execute("INSERT INTO sites(key, name, kind, search_url, notes) VALUES(?,?,'custom',?,?)",
                 (key, name.strip(), search_url.strip(), notes))
    conn.commit()
    return get_site(conn, key)


def update_site(conn, sid: int, data: dict) -> None:
    allowed = {k: data[k] for k in ("name", "search_url", "enabled", "notes") if k in data}
    if "enabled" in allowed:
        allowed["enabled"] = 1 if allowed["enabled"] else 0
    if allowed:
        conn.execute(f"UPDATE sites SET {', '.join(f'{k} = ?' for k in allowed)} WHERE id = ?",
                     (*allowed.values(), sid))
        conn.commit()


def delete_site(conn, sid: int) -> bool:
    cur = conn.execute("DELETE FROM sites WHERE id = ? AND kind = 'custom'", (sid,))
    conn.commit()
    return cur.rowcount > 0


def list_companies(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM companies ORDER BY name COLLATE NOCASE").fetchall()
    return [{**dict(r), "enabled": bool(r["enabled"])} for r in rows]


def create_company(conn, name: str, careers_url: str, notes: str = "") -> dict:
    cur = conn.execute("INSERT INTO companies(name, careers_url, notes) VALUES(?,?,?)",
                       (name.strip(), careers_url.strip(), notes))
    conn.commit()
    return dict(conn.execute("SELECT * FROM companies WHERE id = ?", (cur.lastrowid,)).fetchone())


def set_company_status(conn, cid: int, status: str) -> None:
    conn.execute("UPDATE companies SET last_status = ?, last_checked_at = datetime('now') WHERE id = ?",
                 (status[:300], cid))
    conn.commit()


def get_company(conn, cid: int) -> dict | None:
    r = conn.execute("SELECT * FROM companies WHERE id = ?", (cid,)).fetchone()
    return {**dict(r), "enabled": bool(r["enabled"])} if r else None


def update_company(conn, cid: int, data: dict) -> None:
    allowed = {k: data[k] for k in ("name", "careers_url", "enabled", "adapter", "notes") if k in data}
    if "enabled" in allowed:
        allowed["enabled"] = 1 if allowed["enabled"] else 0
    if allowed:
        conn.execute(f"UPDATE companies SET {', '.join(f'{k} = ?' for k in allowed)} WHERE id = ?",
                     (*allowed.values(), cid))
        conn.commit()


def delete_company(conn, cid: int) -> None:
    conn.execute("DELETE FROM companies WHERE id = ?", (cid,))
    conn.commit()


# ---------------------------------------------------------------- jobs
def _job_out(r: sqlite3.Row) -> dict:
    d = dict(r)
    for f in JOB_JSON_FIELDS:
        if f in d:
            d[f] = json.loads(d[f]) if d[f] else (None if f in ("analysis", "tailor_report") else [])
    return d


def get_job(conn, jid: int) -> dict | None:
    r = conn.execute("SELECT * FROM jobs WHERE id = ?", (jid,)).fetchone()
    return _job_out(r) if r else None


def get_job_by_url(conn, url: str) -> dict | None:
    r = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
    return _job_out(r) if r else None


def insert_job(conn, data: dict, run_id: int | None) -> int:
    """Insert a job. `data` may carry the jd_parse.inspect() fields. Links cross-board duplicates."""
    cols = ("url", "site", "external_id", "title", "company", "location", "work_mode", "job_type",
            "posted_at", "posted_text", "description", "status", "status_note", "employer_type",
            "applicants", "apply_type", "fingerprint")
    vals = [data.get(c, "") or "" for c in cols]
    vals[cols.index("status")] = data.get("status") or "New"
    dup = None
    fp = data.get("fingerprint") or ""
    if fp and not fp.startswith("|") and "||" not in fp:
        r = conn.execute("SELECT id FROM jobs WHERE fingerprint = ? AND duplicate_of IS NULL AND url != ? "
                         "ORDER BY id LIMIT 1", (fp, data["url"])).fetchone()
        dup = r[0] if r else None
    cur = conn.execute(
        f"INSERT INTO jobs({', '.join(cols)}, years_required, auth_flags, duplicate_of, first_run_id) "
        f"VALUES({', '.join('?' * len(cols))}, ?, ?, ?, ?)",
        (*vals, data.get("years_required"), json.dumps(data.get("auth_flags") or []), dup, run_id))
    conn.commit()
    return cur.lastrowid


def touch_job(conn, jid: int) -> None:
    conn.execute("UPDATE jobs SET last_seen_at = datetime('now') WHERE id = ?", (jid,))
    conn.commit()


def get_hit(conn, jid: int, pid: int) -> dict | None:
    return _row(conn.execute("SELECT * FROM job_hits WHERE job_id = ? AND profile_id = ?", (jid, pid)).fetchone())


def upsert_hit(conn, jid: int, pid: int, run_id: int | None, keyword: str, location: str,
               site: str, matched: bool, reason: str) -> None:
    conn.execute("""
        INSERT INTO job_hits(job_id, profile_id, run_id, keyword, location, site, matched, reason)
        VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(job_id, profile_id) DO UPDATE SET
          run_id = excluded.run_id, matched = excluded.matched, reason = excluded.reason,
          seen_at = datetime('now')
    """, (jid, pid, run_id, keyword, location, site, 1 if matched else 0, reason))
    conn.commit()


def list_jobs(conn, *, profile_id=None, site=None, status=None, min_score=None,
              q=None, include_filtered=False, limit=500) -> list[dict]:
    where, args = [], []
    hit_cond = "h.job_id = j.id" + ("" if include_filtered else " AND h.matched = 1")
    if profile_id:
        hit_cond += " AND h.profile_id = ?"
        args.append(int(profile_id))
    where.append(f"EXISTS (SELECT 1 FROM job_hits h WHERE {hit_cond})")
    where.append("j.duplicate_of IS NULL")
    if site:
        where.append("j.site = ?"); args.append(site)
    if status:
        where.append("j.status = ?"); args.append(status)
    if min_score not in (None, ""):
        where.append("COALESCE(j.match_score, 0) >= ?"); args.append(int(min_score))
    if q:
        where.append("(j.title LIKE ? OR j.company LIKE ? OR j.location LIKE ?)")
        args += [f"%{q}%"] * 3
    sql = f"""
        SELECT j.id, j.url, j.site, j.title, j.company, j.location, j.work_mode, j.job_type,
               j.posted_at, j.posted_text, j.status, j.status_note, j.match_score,
               j.matched_keywords, j.missing_keywords, j.analyzed_at, j.first_seen_at,
               j.tailored_docx, j.tailored_pdf, j.tailored_at, j.years_required, j.auth_flags, j.employer_type,
               j.applicants, j.apply_type,
               (SELECT group_concat(DISTINCT d.site) FROM jobs d WHERE d.duplicate_of = j.id) AS also_on,
               (SELECT group_concat(p.name, ', ') FROM job_hits h JOIN profiles p ON p.id = h.profile_id
                 WHERE h.job_id = j.id AND h.matched = 1) AS profiles,
               (SELECT group_concat(DISTINCT h.reason) FROM job_hits h
                 WHERE h.job_id = j.id AND h.matched = 0) AS filtered_reason
        FROM jobs j WHERE {' AND '.join(where)}
        ORDER BY date(j.first_seen_at) DESC, COALESCE(j.match_score, -1) DESC, j.posted_at DESC
        LIMIT ?
    """
    args.append(int(limit))
    return [_job_out(r) for r in conn.execute(sql, args).fetchall()]


def set_job_status(conn, jid: int, status: str, note: str = "") -> None:
    conn.execute("UPDATE jobs SET status = ?, status_note = ? WHERE id = ?", (status, note, jid))
    conn.commit()


def save_analysis(conn, jid: int, resume_id: int, analysis: dict) -> None:
    conn.execute("""
        UPDATE jobs SET resume_id = ?, match_score = ?, matched_keywords = ?, missing_keywords = ?,
               analysis = ?, analyzed_at = datetime('now')
        WHERE id = ?
    """, (resume_id, int(analysis.get("score") or 0), json.dumps(analysis.get("matched") or []),
          json.dumps(analysis.get("missing") or []), json.dumps(analysis), jid))
    conn.commit()


def save_tailoring(conn, jid: int, docx_path: str, pdf_path: str | None, report: dict,
                   cover_note: str | None, cover_note_path: str | None) -> None:
    conn.execute("""
        UPDATE jobs SET tailored_docx = ?, tailored_pdf = ?, tailor_report = ?, tailored_at = datetime('now'),
               cover_note = ?, cover_note_path = ?,
               status = CASE WHEN status IN ('New', 'Failed') THEN 'Tailored' ELSE status END
        WHERE id = ?""", (docx_path, pdf_path, json.dumps(report), cover_note, cover_note_path, jid))
    conn.commit()


def tailor_candidates(conn, run_id: int) -> list[int]:
    """Jobs matched in this run, analyzed, not yet tailored, scoring at least their profile's minimum."""
    return [r[0] for r in conn.execute("""
        SELECT DISTINCT j.id FROM jobs j
        JOIN job_hits h ON h.job_id = j.id AND h.matched = 1 AND h.run_id = ?
        JOIN profiles p ON p.id = h.profile_id
        WHERE j.duplicate_of IS NULL AND j.analyzed_at IS NOT NULL AND j.tailored_at IS NULL
          AND j.status NOT IN ('Skipped', 'Applied') AND COALESCE(j.match_score, 0) >= p.min_score
        ORDER BY j.match_score DESC""", (run_id,))]


def resume_for_job(conn, jid: int) -> dict | None:
    """The base resume of the first matching profile, else the default resume."""
    r = conn.execute("""
        SELECT r.* FROM job_hits h JOIN profiles p ON p.id = h.profile_id JOIN resumes r ON r.id = p.resume_id
        WHERE h.job_id = ? AND h.matched = 1 ORDER BY h.seen_at LIMIT 1
    """, (jid,)).fetchone()
    return _row(r) or default_resume(conn)


def unanalyzed_matched_job_ids(conn, run_id: int | None = None) -> list[int]:
    sql = """SELECT DISTINCT j.id FROM jobs j JOIN job_hits h ON h.job_id = j.id AND h.matched = 1
             WHERE j.analyzed_at IS NULL AND j.description != '' AND j.duplicate_of IS NULL"""
    args: tuple = ()
    if run_id:
        sql += " AND h.run_id = ?"
        args = (run_id,)
    return [r[0] for r in conn.execute(sql + " ORDER BY j.id", args)]


# ---------------------------------------------------------------- applications
APP_STATUSES = ["Applied", "Screening", "Interview", "Offer", "Rejected", "No response", "Withdrawn"]
_ACTIVE = ("Applied", "Screening", "Interview")


def _app_out(r) -> dict:
    d = dict(r)
    d["history"] = json.loads(d.get("history") or "[]")
    return d


def mark_applied(conn, jid: int, *, applied_on: str | None, channel: str, notes: str, follow_up_days: int,
                 resume_file: str | None) -> dict:
    when = applied_on or None
    existing = conn.execute("SELECT id FROM applications WHERE job_id = ?", (jid,)).fetchone()
    if existing:
        raise ValueError("Already marked as applied (see Applications).")
    conn.execute("""
        INSERT INTO applications(job_id, applied_at, status, resume_file, follow_up_on, notes, channel, history, updated_at)
        VALUES(?, COALESCE(?, datetime('now')), 'Applied', ?, date(COALESCE(?, 'now'), ?), ?, ?, ?, datetime('now'))""",
                 (jid, when, resume_file, when, f"+{int(follow_up_days)} days", notes, channel,
                  json.dumps([{"status": "Applied", "at": when or "", "note": notes}])))
    conn.execute("UPDATE jobs SET status = 'Applied', status_note = '' WHERE id = ?", (jid,))
    conn.commit()
    return get_application_by_job(conn, jid)


def get_application(conn, aid: int) -> dict | None:
    r = conn.execute("SELECT * FROM applications WHERE id = ?", (aid,)).fetchone()
    return _app_out(r) if r else None


def get_application_by_job(conn, jid: int) -> dict | None:
    r = conn.execute("SELECT * FROM applications WHERE job_id = ?", (jid,)).fetchone()
    return _app_out(r) if r else None


def update_application(conn, aid: int, data: dict) -> dict | None:
    a = get_application(conn, aid)
    if not a:
        return None
    sets, args = [], []
    if "status" in data and data["status"] != a["status"]:
        if data["status"] not in APP_STATUSES:
            raise ValueError(f"status must be one of {APP_STATUSES}")
        hist = a["history"] + [{"status": data["status"], "at": "", "note": data.get("note", "")}]
        sets += ["status = ?", "history = ?"]
        args += [data["status"], json.dumps(hist)]
        if data["status"] in ("Screening", "Interview", "Offer", "Rejected") and not a["response_at"]:
            sets.append("response_at = datetime('now')")
        if data["status"] not in _ACTIVE:
            sets.append("follow_up_on = NULL")
    for k in ("notes", "follow_up_on", "channel"):
        if k in data:
            sets.append(f"{k} = ?")
            args.append(data[k] or None if k == "follow_up_on" else data[k])
    if sets:
        conn.execute(f"UPDATE applications SET {', '.join(sets)}, updated_at = datetime('now') WHERE id = ?", (*args, aid))
        conn.execute("UPDATE applications SET history = json_set(history, '$[#-1].at', datetime('now')) "
                     "WHERE id = ? AND json_extract(history, '$[#-1].at') = ''", (aid,))
        conn.commit()
    return get_application(conn, aid)


def delete_application(conn, aid: int) -> None:
    a = get_application(conn, aid)
    if not a:
        return
    conn.execute("DELETE FROM applications WHERE id = ?", (aid,))
    conn.execute("UPDATE jobs SET status = CASE WHEN tailored_at IS NOT NULL THEN 'Tailored' ELSE 'New' END "
                 "WHERE id = ?", (a["job_id"],))
    conn.commit()


def list_applications(conn, status: str | None = None, q: str | None = None) -> list[dict]:
    where, args = ["1 = 1"], []
    if status == "active":
        where.append("a.status IN ('Applied', 'Screening', 'Interview')")
    elif status:
        where.append("a.status = ?")
        args.append(status)
    if q:
        where.append("(j.title LIKE ? OR j.company LIKE ?)")
        args += [f"%{q}%"] * 2
    rows = conn.execute(f"""
        SELECT a.*, j.title, j.company, j.location, j.site, j.url, j.match_score, j.tailored_docx, j.tailored_pdf,
               j.work_mode, j.job_type,
               CASE WHEN a.follow_up_on IS NOT NULL AND a.follow_up_on <= date('now')
                         AND a.status IN ('Applied', 'Screening', 'Interview') THEN 1 ELSE 0 END AS follow_up_due,
               CAST(julianday('now') - julianday(a.applied_at) AS INTEGER) AS days_since
        FROM applications a JOIN jobs j ON j.id = a.job_id
        WHERE {' AND '.join(where)} ORDER BY follow_up_due DESC, a.applied_at DESC""", args).fetchall()
    return [_app_out(r) for r in rows]


def application_counts(conn) -> dict:
    out = {s: 0 for s in APP_STATUSES}
    for r in conn.execute("SELECT status, COUNT(*) FROM applications GROUP BY status"):
        out[r[0]] = r[1]
    out["follow_up_due"] = conn.execute(
        "SELECT COUNT(*) FROM applications WHERE follow_up_on <= date('now') "
        "AND status IN ('Applied', 'Screening', 'Interview')").fetchone()[0]
    return out


# ---------------------------------------------------------------- runs
def create_run(conn, kind: str, *, profile_id=None, job_id=None, trigger="manual",
               uses_browser=True, status="queued") -> int:
    cur = conn.execute(
        "INSERT INTO runs(kind, profile_id, job_id, trigger, uses_browser, status) VALUES(?,?,?,?,?,?)",
        (kind, profile_id, job_id, trigger, 1 if uses_browser else 0, status))
    conn.commit()
    return cur.lastrowid


def _run_out(r):
    d = _row(r)
    if d and d.get("payload"):
        d["payload"] = json.loads(d["payload"])
    return d


def get_run(conn, rid: int) -> dict | None:
    return _run_out(conn.execute("""
        SELECT r.*, p.name AS profile_name, j.title AS job_title
        FROM runs r LEFT JOIN profiles p ON p.id = r.profile_id LEFT JOIN jobs j ON j.id = r.job_id
        WHERE r.id = ?""", (rid,)).fetchone())


def list_runs(conn, limit=50) -> list[dict]:
    return [dict(r) for r in conn.execute("""
        SELECT r.*, p.name AS profile_name, j.title AS job_title
        FROM runs r LEFT JOIN profiles p ON p.id = r.profile_id LEFT JOIN jobs j ON j.id = r.job_id
        ORDER BY r.id DESC LIMIT ?""", (limit,))]


def active_runs(conn) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM runs WHERE status IN ('queued','running','waiting_user') ORDER BY id")]


def update_run(conn, rid: int, **fields) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    if fields.get("status") in ("done", "failed", "cancelled"):
        sets += ", finished_at = datetime('now')"
    conn.execute(f"UPDATE runs SET {sets} WHERE id = ?", (*fields.values(), rid))
    conn.commit()


def bump_run(conn, rid: int, seen=0, new=0, matched=0) -> None:
    conn.execute("UPDATE runs SET jobs_seen = jobs_seen + ?, jobs_new = jobs_new + ?, "
                 "jobs_matched = jobs_matched + ? WHERE id = ?", (seen, new, matched, rid))
    conn.commit()


def set_run_payload(conn, rid: int, payload: dict) -> None:
    conn.execute("UPDATE runs SET payload = ? WHERE id = ?", (json.dumps(payload), rid))
    conn.commit()


def send_command(conn, rid: int, command: str) -> None:
    conn.execute("UPDATE runs SET command = ? WHERE id = ?", (command, rid))
    conn.commit()


def take_command(conn, rid: int) -> str | None:
    r = conn.execute("SELECT command FROM runs WHERE id = ?", (rid,)).fetchone()
    if r and r[0]:
        conn.execute("UPDATE runs SET command = NULL WHERE id = ?", (rid,))
        conn.commit()
        return r[0]
    return None


def applied_today(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM applications WHERE date(applied_at, 'localtime') = date('now', 'localtime') "
                        "OR date(applied_at) = date('now')").fetchone()[0]


def cancel_requested(conn, rid: int) -> bool:
    r = conn.execute("SELECT cancel_requested FROM runs WHERE id = ?", (rid,)).fetchone()
    return bool(r and r[0])
