"""FastAPI backend. Serves /api/* and the built Angular app at /. Binds to 127.0.0.1 only."""
from __future__ import annotations

import re
import sqlite3
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse

import shutil

from . import (applicant, auth, claude_cli, db, notify, options, paths, pdf, repo, resume_check, resume_designs,
               resume_doc, resume_insights, runs, scheduler, settings, stats, tailor)
from .resume_text import docx_to_text
from .scrapers.registry import LOGIN_URLS, implemented
from .textutil import slug

MAX_RESUME_BYTES = 5 * 1024 * 1024


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    yield


app = FastAPI(title="Job Assist", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)


def get_conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def _404(what: str):
    raise HTTPException(404, f"{what} not found")


# ------------------------------------------------------------------ meta & settings
@app.get("/api/meta")
def meta(conn=Depends(get_conn)):
    s = settings.load(conn)
    return {**options.meta(), "implemented_sites": implemented(), "claude_cli": claude_cli.available(),
            "analysis_engine": s["analysis_engine"]}


@app.get("/api/settings")
def get_settings(conn=Depends(get_conn)):
    return {"spec": settings.SPEC, "values": settings.load(conn)}


@app.put("/api/settings")
def put_settings(values: dict = Body(...), conn=Depends(get_conn)):
    try:
        return {"spec": settings.SPEC, "values": settings.save(conn, values)}
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))


# ------------------------------------------------------------------ profiles
@app.get("/api/profiles")
def profiles(conn=Depends(get_conn)):
    return repo.list_profiles(conn)


@app.get("/api/profiles/{pid}")
def profile(pid: int, conn=Depends(get_conn)):
    return repo.get_profile(conn, pid) or _404("Profile")


@app.post("/api/profiles")
def create_profile(data: dict = Body(...), conn=Depends(get_conn)):
    try:
        return repo.create_profile(conn, data)
    except sqlite3.IntegrityError:
        raise HTTPException(400, "A profile with that name already exists")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.put("/api/profiles/{pid}")
def update_profile(pid: int, data: dict = Body(...), conn=Depends(get_conn)):
    try:
        return repo.update_profile(conn, pid, data) or _404("Profile")
    except sqlite3.IntegrityError:
        raise HTTPException(400, "A profile with that name already exists")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/profiles/{pid}/duplicate")
def duplicate_profile(pid: int, conn=Depends(get_conn)):
    return repo.duplicate_profile(conn, pid) or _404("Profile")


@app.delete("/api/profiles/{pid}")
def delete_profile(pid: int, conn=Depends(get_conn)):
    repo.delete_profile(conn, pid)
    return {"ok": True}


@app.post("/api/profiles/{pid}/run")
def run_profile(pid: int, conn=Depends(get_conn)):
    if not repo.get_profile(conn, pid):
        _404("Profile")
    return _start(conn, "search", profile_id=pid)


# ------------------------------------------------------------------ resumes
@app.get("/api/resumes")
def resumes(conn=Depends(get_conn)):
    custom = settings.load(conn).get("custom_skills", "")
    out = []
    for r in repo.list_resumes(conn):
        text = (repo.get_resume(conn, r["id"]) or {}).get("text", "")
        exp = resume_insights.estimate_experience(text)
        out.append({**r, "top_skills": [s["name"] for s in resume_insights.top_skills(text, custom, 8)],
                    "years_estimate": exp["years"]})
    return out


@app.get("/api/resumes/{rid}/suggestions")
def resume_suggestions(rid: int, profile_id: int | None = None, conn=Depends(get_conn)):
    r = repo.get_resume(conn, rid) or _404("Resume")
    profile = repo.get_profile(conn, profile_id) if profile_id else None
    return {"resume": {"id": r["id"], "name": r["name"]},
            **resume_insights.suggest(r["text"], settings.load(conn), profile)}


@app.post("/api/resumes")
def upload_resume(file: UploadFile = File(...), name: str = Form(""), conn=Depends(get_conn)):
    """Word (.docx/.doc) or PDF. Non-Word files are converted to .docx once; the original is kept too."""
    original = Path(file.filename or "resume.docx").name
    ext = Path(original).suffix.lower()
    if ext not in resume_doc.SUPPORTED:
        raise HTTPException(400, "Please upload your resume as Word (.docx or .doc) or PDF.")
    data = file.file.read()
    if len(data) > MAX_RESUME_BYTES:
        raise HTTPException(400, "File is larger than 5 MB")
    display = (name or Path(original).stem).strip()
    base = f"{slug(display)}_{uuid.uuid4().hex[:8]}"
    paths.ensure_dirs()
    src = paths.RESUMES / f"{base}_original{ext}" if ext != ".docx" else paths.RESUMES / f"{base}.docx"
    src.write_bytes(data)
    dest = paths.RESUMES / f"{base}.docx"
    try:
        how = resume_doc.to_docx(src, dest) if ext != ".docx" else "docx"
        text = docx_to_text(dest)
    except Exception as e:
        for f in (src, dest):
            f.unlink(missing_ok=True)
        raise HTTPException(400, str(e) if isinstance(e, ValueError) else f"Could not read that file: {e}")
    if not text.strip():
        for f in (src, dest):
            f.unlink(missing_ok=True)
        raise HTTPException(400, "That resume has no readable text (is it a scanned image?)")
    return repo.create_resume(conn, display, dest.name, original, text, source_ext=ext,
                              source_file=src.name if ext != ".docx" else None,
                              converted_by="" if how == "docx" else how)


def _resume_path(r: dict) -> Path:
    return paths.RESUMES / r["file_name"]


@app.get("/api/resumes/{rid}/check")
def resume_check_api(rid: int, conn=Depends(get_conn)):
    r = repo.get_resume(conn, rid) or _404("Resume")
    rd = resume_doc.parse(_resume_path(r))
    return resume_check.check(rd, settings.load(conn).get("custom_skills", ""), r.get("source_ext") or ".docx")


@app.post("/api/resumes/{rid}/designs")
def resume_designs_api(rid: int, conn=Depends(get_conn)):
    """Render every design for this resume into a preview folder and make PDF previews."""
    r = repo.get_resume(conn, rid) or _404("Resume")
    folder = paths.DATA / "previews" / f"resume_{rid}"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    rd = resume_doc.parse(_resume_path(r))
    built = resume_designs.build_all(rd, docx_to_text(_resume_path(r)), folder, "design")
    method = None
    try:
        method = pdf.folder_to_pdf([Path(b["docx"]) for b in built], settings.load(conn).get("browser_channel", "chrome"))
    except Exception:
        pass
    return {"pdf_method": method, "designs": [
        {k: v for k, v in b.items() if k != "docx"} | {"preview": f"/api/resumes/{rid}/designs/{b['key']}/preview.pdf"
                                                        if Path(b["docx"]).with_suffix(".pdf").exists() else None}
        for b in built]}


@app.get("/api/resumes/{rid}/designs/{key}/preview.pdf")
def resume_design_preview(rid: int, key: str):
    if key not in resume_designs.DESIGNS:
        _404("Design")
    f = paths.DATA / "previews" / f"resume_{rid}" / f"design_{key}.pdf"
    if not f.exists():
        _404("Preview")
    return FileResponse(f, media_type="application/pdf", headers={"Content-Disposition": "inline"})


@app.post("/api/resumes/{rid}/designs/{key}/use")
def resume_design_use(rid: int, key: str, data: dict = Body(default={}), conn=Depends(get_conn)):
    """Save the chosen design as a NEW base resume. The original stays untouched."""
    r = repo.get_resume(conn, rid) or _404("Resume")
    if key not in resume_designs.DESIGNS:
        _404("Design")
    src = paths.DATA / "previews" / f"resume_{rid}" / f"design_{key}.docx"
    if not src.exists():
        raise HTTPException(400, "Open the designs again first.")
    label = resume_designs.DESIGNS[key]["label"]
    display = (str(data.get("name") or "").strip() or f"{r['name']} ({label})")[:80]
    stored = f"{slug(display)}_{uuid.uuid4().hex[:8]}.docx"
    shutil.copyfile(src, paths.RESUMES / stored)
    new = repo.create_resume(conn, display, stored, f"{label} design of {r['original_name']}",
                             docx_to_text(paths.RESUMES / stored), design=key, parent_id=rid)
    if data.get("make_default"):
        repo.set_default_resume(conn, new["id"])
    return new


@app.get("/api/resumes/{rid}")
def resume(rid: int, conn=Depends(get_conn)):
    return repo.get_resume(conn, rid) or _404("Resume")


@app.put("/api/resumes/{rid}")
def rename_resume(rid: int, data: dict = Body(...), conn=Depends(get_conn)):
    name = str(data.get("name", "")).strip()
    if not name:
        raise HTTPException(400, "Name is required")
    repo.rename_resume(conn, rid, name)
    return repo.get_resume(conn, rid) or _404("Resume")


@app.post("/api/resumes/{rid}/default")
def default_resume(rid: int, conn=Depends(get_conn)):
    if not repo.get_resume(conn, rid):
        _404("Resume")
    repo.set_default_resume(conn, rid)
    return {"ok": True}


@app.get("/api/resumes/{rid}/file")
def resume_file(rid: int, conn=Depends(get_conn)):
    r = repo.get_resume(conn, rid) or _404("Resume")
    nice = Path(r["original_name"] or r["file_name"]).stem + ".docx"
    return FileResponse(paths.RESUMES / r["file_name"], filename=nice)


@app.delete("/api/resumes/{rid}")
def delete_resume(rid: int, conn=Depends(get_conn)):
    r = repo.delete_resume(conn, rid) or _404("Resume")
    (paths.RESUMES / r["file_name"]).unlink(missing_ok=True)
    if r.get("source_file"):
        (paths.RESUMES / r["source_file"]).unlink(missing_ok=True)
    return {"ok": True}


# ------------------------------------------------------------------ sites & companies
@app.get("/api/sites")
def sites(conn=Depends(get_conn)):
    return repo.list_sites(conn)


@app.post("/api/sites")
def create_site(data: dict = Body(...), conn=Depends(get_conn)):
    name, url = str(data.get("name", "")).strip(), str(data.get("search_url", "")).strip()
    if not name or not re.match(r"^https?://", url):
        raise HTTPException(400, "Give a name and a search URL starting with http(s)://")
    return repo.create_site(conn, name, url, str(data.get("notes", "")))


@app.put("/api/sites/{sid}")
def update_site(sid: int, data: dict = Body(...), conn=Depends(get_conn)):
    repo.update_site(conn, sid, data)
    return {"ok": True}


@app.delete("/api/sites/{sid}")
def delete_site(sid: int, conn=Depends(get_conn)):
    if not repo.delete_site(conn, sid):
        raise HTTPException(400, "Built-in sites can be disabled but not deleted")
    return {"ok": True}


@app.get("/api/companies")
def companies(conn=Depends(get_conn)):
    return repo.list_companies(conn)


@app.post("/api/companies")
def create_company(data: dict = Body(...), conn=Depends(get_conn)):
    name, url = str(data.get("name", "")).strip(), str(data.get("careers_url", "")).strip()
    if not name or not re.match(r"^https?://", url):
        raise HTTPException(400, "Give a company name and a careers URL starting with http(s)://")
    try:
        return repo.create_company(conn, name, url, str(data.get("notes", "")))
    except sqlite3.IntegrityError:
        raise HTTPException(400, "That careers URL is already in the list")


@app.get("/api/adapters")
def adapters():
    return sorted(p.stem for p in paths.ADAPTERS.glob("*.py") if not p.stem.startswith("_"))


@app.put("/api/companies/{cid}")
def update_company(cid: int, data: dict = Body(...), conn=Depends(get_conn)):
    repo.update_company(conn, cid, data)
    return {"ok": True}


@app.delete("/api/companies/{cid}")
def delete_company(cid: int, conn=Depends(get_conn)):
    repo.delete_company(conn, cid)
    return {"ok": True}


# ------------------------------------------------------------------ jobs
@app.get("/api/jobs")
def jobs(profile_id: int | None = None, site: str | None = None, status: str | None = None,
         min_score: int | None = None, q: str | None = None, include_filtered: bool = False,
         conn=Depends(get_conn)):
    return repo.list_jobs(conn, profile_id=profile_id, site=site, status=status, min_score=min_score,
                          q=q, include_filtered=include_filtered)


@app.get("/api/jobs/{jid}")
def job(jid: int, conn=Depends(get_conn)):
    j = repo.get_job(conn, jid) or _404("Job")
    j["hits"] = [dict(r) for r in conn.execute(
        "SELECT h.*, p.name AS profile_name FROM job_hits h JOIN profiles p ON p.id = h.profile_id "
        "WHERE h.job_id = ?", (jid,))]
    return j


@app.patch("/api/jobs/{jid}")
def patch_job(jid: int, data: dict = Body(...), conn=Depends(get_conn)):
    status = data.get("status")
    if status not in options.JOB_STATUSES:
        raise HTTPException(400, f"status must be one of {options.JOB_STATUSES}")
    if status == "Applied":
        raise HTTPException(400, "Use 'Mark as applied' so the application is logged with its date and resume")
    repo.set_job_status(conn, jid, status, str(data.get("note", "")))
    return repo.get_job(conn, jid) or _404("Job")


@app.post("/api/jobs/analyze")
def analyze_jobs(data: dict = Body(default={}), conn=Depends(get_conn)):
    ids = [int(i) for i in data.get("job_ids", [])]
    return _start(conn, "analyze", job_ids=ids)


@app.post("/api/jobs/{jid}/tailor")
def tailor_job(jid: int, conn=Depends(get_conn)):
    if not repo.get_job(conn, jid):
        _404("Job")
    return _start(conn, "tailor", job_ids=[jid])


@app.get("/api/jobs/{jid}/file/{kind}")
def tailored_file(jid: int, kind: str, conn=Depends(get_conn)):
    j = repo.get_job(conn, jid) or _404("Job")
    col = {"docx": "tailored_docx", "pdf": "tailored_pdf", "cover": "cover_note_path"}.get(kind)
    path = Path(j[col]) if col and j.get(col) else None
    if not path or not path.exists() or paths.TAILORED.resolve() not in path.resolve().parents:
        _404("File")
    return FileResponse(path, filename=path.name)


@app.post("/api/jobs/{jid}/rename-tailored")
def rename_tailored_api(jid: int, data: dict = Body(...), conn=Depends(get_conn)):
    try:
        return tailor.rename_tailored(conn, jid, str(data.get("name", "")))
    except (ValueError, OSError) as e:
        raise HTTPException(400, str(e))


# ------------------------------------------------------------------ applications
@app.post("/api/jobs/{jid}/applied")
def mark_applied(jid: int, data: dict = Body(default={}), conn=Depends(get_conn)):
    j = repo.get_job(conn, jid) or _404("Job")
    s = settings.load(conn)
    used = j.get("tailored_pdf") or j.get("tailored_docx")
    if not used:
        base = repo.resume_for_job(conn, jid)
        used = str(paths.RESUMES / base["file_name"]) if base else None
    try:
        return repo.mark_applied(conn, jid, applied_on=data.get("applied_on") or None,
                                 channel=str(data.get("channel", "")), notes=str(data.get("notes", "")),
                                 follow_up_days=int(s["follow_up_days"]), resume_file=used)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/applications")
def applications(status: str | None = None, q: str | None = None, conn=Depends(get_conn)):
    return {"items": repo.list_applications(conn, status, q), "counts": repo.application_counts(conn),
            "statuses": repo.APP_STATUSES}


@app.patch("/api/applications/{aid}")
def update_application(aid: int, data: dict = Body(...), conn=Depends(get_conn)):
    try:
        return repo.update_application(conn, aid, data) or _404("Application")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/applications/{aid}")
def delete_application(aid: int, conn=Depends(get_conn)):
    repo.delete_application(conn, aid)
    return {"ok": True}


@app.get("/api/applications.csv")
def applications_csv(conn=Depends(get_conn)):
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Applied on", "Status", "Company", "Role", "Location", "Site", "Job link", "Match score",
                "Resume sent", "Follow up on", "Response on", "Channel", "Notes"])
    for a in repo.list_applications(conn):
        w.writerow([a["applied_at"][:10], a["status"], a["company"], a["title"], a["location"], a["site"], a["url"],
                    a["match_score"] if a["match_score"] is not None else "", Path(a["resume_file"]).name if a["resume_file"] else "",
                    a["follow_up_on"] or "", (a["response_at"] or "")[:10], a["channel"], a["notes"]])
    return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=job_applications.csv"})


# ------------------------------------------------------------------ stats, schedule, notifications
@app.get("/api/stats")
def stats_api(conn=Depends(get_conn)):
    return stats.all_stats(conn, settings.load(conn))


@app.get("/api/schedule")
def schedule_get(conn=Depends(get_conn)):
    t = settings.load(conn)["schedule_time"]
    return {**scheduler.status(), "time": t, "command": scheduler.manual_command(t), "task_name": scheduler.TASK_NAME}


@app.post("/api/schedule")
def schedule_set(data: dict = Body(...), conn=Depends(get_conn)):
    t = str(data.get("time") or settings.load(conn)["schedule_time"])
    if not scheduler.valid_time(t):
        raise HTTPException(400, "Time must be HH:MM, e.g. 08:00")
    settings.save(conn, {"schedule_time": t})
    try:
        scheduler.enable(t) if data.get("enabled") else scheduler.disable()
    except Exception as e:
        raise HTTPException(400, f"Windows Task Scheduler: {e}")
    return schedule_get(conn)


@app.post("/api/notify/test")
def notify_test():
    ok = notify.toast("Job Assist", "Notifications are working. Click to open the app.", "/settings")
    if not ok:
        raise HTTPException(400, "Windows didn't show the notification. Check Windows Settings > System > Notifications.")
    return {"ok": True}


# ------------------------------------------------------------------ apply-assist
@app.get("/api/applicant")
def get_applicant(conn=Depends(get_conn)):
    return {"spec": applicant.SPEC, "values": applicant.load(settings.load(conn))}


@app.put("/api/applicant")
def put_applicant(data: dict = Body(...), conn=Depends(get_conn)):
    return {"spec": applicant.SPEC, "values": applicant.save(data)}


@app.post("/api/jobs/{jid}/apply")
def apply_job(jid: int, conn=Depends(get_conn)):
    if not repo.get_job(conn, jid):
        _404("Job")
    missing = applicant.missing_basics(applicant.load(settings.load(conn)))
    if missing:
        raise HTTPException(400, "Fill in My details first (missing: " + ", ".join(missing) + ").")
    cap = int(settings.load(conn)["daily_apply_cap"])
    if repo.applied_today(conn) >= cap:
        raise HTTPException(400, f"Daily limit reached ({cap} today). You can change it in Settings.")
    return _start(conn, "apply", job_ids=[jid])


@app.post("/api/runs/{rid}/command")
def run_command(rid: int, data: dict = Body(...), conn=Depends(get_conn)):
    cmd = data.get("command")
    if cmd not in ("submit", "done", "refill", "cancel"):
        raise HTTPException(400, "Unknown command")
    r = repo.get_run(conn, rid) or _404("Run")
    if r["status"] not in ("running", "waiting_user"):
        raise HTTPException(400, "That application session has ended.")
    repo.send_command(conn, rid, cmd)
    return {"ok": True}


@app.post("/api/jobs/{jid}/tailor-apply")
def tailor_apply(jid: int, conn=Depends(get_conn)):
    if not repo.get_job(conn, jid):
        _404("Job")
    return _start(conn, "tailor_apply", job_ids=[jid])


# ------------------------------------------------------------------ runs
def _start(conn, kind, **kw) -> dict:
    try:
        return runs.start(conn, kind, **kw)
    except runs.RunConflict as e:
        raise HTTPException(409, str(e))


@app.post("/api/runs/search-all")
def run_all(conn=Depends(get_conn)):
    return _start(conn, "search")


@app.post("/api/runs/login")
def run_login(data: dict = Body(default={}), conn=Depends(get_conn)):
    return _start(conn, "login", extra={"login_key": data.get("login_key")})


@app.post("/api/companies/{cid}/test")
def test_company(cid: int, data: dict = Body(default={}), conn=Depends(get_conn)):
    if not repo.get_company(conn, cid):
        _404("Company")
    return _start(conn, "company_test", extra={"company_id": cid, "keyword": data.get("keyword")})


# ------------------------------------------------------------------ logins (passwords never leave keyring)
@app.get("/api/logins")
def logins(conn=Depends(get_conn)):
    saved = auth.list_logins(conn)
    rows = [(s["key"], s["name"], LOGIN_URLS[s["key"]]) for s in repo.list_sites(conn) if s["key"] in LOGIN_URLS]
    rows += [(f"company_{c['id']}", c["name"], c["careers_url"]) for c in repo.list_companies(conn)]
    out = []
    for key, name, url in rows:
        r = saved.get(key) or {}
        mode = r.get("mode", "manual")
        out.append({"login_key": key, "name": name, "url": url, "mode": mode, "username": r.get("username", ""),
                    "password_saved": mode == "saved" and auth.has_password(conn, key)})
    return out


@app.put("/api/logins/{key}")
def save_login(key: str, data: dict = Body(...), conn=Depends(get_conn)):
    if not re.fullmatch(r"[a-z]+|company_\d+", key):
        raise HTTPException(400, "Unknown login")
    try:
        auth.save_login(conn, key, data.get("mode", "manual"), data.get("username", ""), data.get("password") or None)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # keyring backend problems
        raise HTTPException(500, f"Windows Credential Manager error: {type(e).__name__}")
    return {"ok": True}


@app.get("/api/runs")
def list_runs(conn=Depends(get_conn)):
    runs.reconcile(conn)
    return repo.list_runs(conn)


@app.get("/api/runs/active")
def active(conn=Depends(get_conn)):
    runs.reconcile(conn)
    return [repo.get_run(conn, r["id"]) for r in repo.active_runs(conn)]


@app.get("/api/runs/{rid}")
def get_run(rid: int, conn=Depends(get_conn)):
    return repo.get_run(conn, rid) or _404("Run")


@app.get("/api/runs/{rid}/log", response_class=PlainTextResponse)
def run_log(rid: int, conn=Depends(get_conn)):
    r = repo.get_run(conn, rid) or _404("Run")
    return runs.read_log(r)


@app.post("/api/runs/{rid}/stop")
def stop_run(rid: int, conn=Depends(get_conn)):
    runs.stop(conn, rid)
    return {"ok": True}


# ------------------------------------------------------------------ Angular app
@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(404)
    if not paths.WEB_DIST.exists():
        return HTMLResponse("<h2>UI not built yet</h2><p>Run <code>cd web</code> then "
                            "<code>npm run build</code>, and reload.</p>", status_code=503)
    target = (paths.WEB_DIST / full_path).resolve()
    if full_path and target.is_file() and paths.WEB_DIST.resolve() in target.parents:
        return FileResponse(target)  # hashed bundle names, safe to cache
    # index.html must never be cached, or users keep seeing old screens after an update
    return FileResponse(paths.WEB_DIST / "index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


def main() -> None:
    import uvicorn
    uvicorn.run("jobassist.api:app", host="127.0.0.1", port=8770, log_level="warning")


if __name__ == "__main__":
    main()
