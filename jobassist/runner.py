"""Background worker. The UI starts it as a separate process; Task Scheduler calls it directly.

  python -m jobassist.runner search [--profile-id N] [--trigger schedule]
  python -m jobassist.runner login
  python -m jobassist.runner analyze [--job-id N ...]
  python -m jobassist.runner tailor-apply --job-id N

When the UI starts a run it passes --run-id (the row already exists). When started by hand or by
Task Scheduler, the runner creates its own run row and log file.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import traceback

from pathlib import Path

from . import analysis, db, paths, repo, runs
from .scrapers.base import BudgetExhausted, Cancelled, RunContext
from .scrapers.registry import LOGIN_URLS
from .settings import load as load_settings

log = logging.getLogger("jobassist")


def _setup_logging(log_file: str | None) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")
    log.setLevel(logging.INFO)
    log.handlers.clear()
    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
    else:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        log.addHandler(sh)


# ------------------------------------------------------------------ kinds
def do_search(conn, run, settings) -> str:
    from .engine import run_profile
    from .scrapers.browser import open_browser

    if run["profile_id"]:
        p = repo.get_profile(conn, run["profile_id"])
        profiles = [p] if p else []
    else:
        profiles = [p for p in repo.list_profiles(conn) if p["enabled"]]
    if not profiles:
        return "No enabled profiles to run."

    ctx = RunContext(conn, run["id"], settings)
    totals = {"seen": 0, "new": 0, "matched": 0}
    with open_browser(settings["headless"], int(settings["page_timeout_sec"]), settings["browser_channel"]) as browser:
        for p in profiles:
            try:
                c = run_profile(ctx, browser, p)
            except BudgetExhausted:
                break
            for k in totals:
                totals[k] += c[k]
            ctx.delay()
    summary = f"{totals['seen']} jobs seen, {totals['new']} new, {totals['matched']} matched"
    log.info(summary)

    if settings["auto_analyze"] and totals["matched"]:
        n = _analyze_ids(conn, ctx, repo.unanalyzed_matched_job_ids(conn, run["id"]), settings)
        summary += f", {n} analyzed"
        if settings.get("auto_tailor"):
            n = _tailor_ids(conn, ctx, repo.tailor_candidates(conn, run["id"]), settings)
            if n:
                summary += f", {n} resume(s) tailored"
    return summary


def _tailor_ids(conn, ctx: RunContext, ids: list[int], settings) -> int:
    from . import tailor

    done = 0
    for i, jid in enumerate(ids, 1):
        ctx.check_cancel()
        ctx.status("running", f"Tailoring resume {i} of {len(ids)}")
        try:
            tailor.tailor_job(conn, jid, settings, log=log.info)
            done += 1
        except Exception as e:  # one bad job must not stop the rest
            log.warning(f"  tailoring failed for job {jid}: {e}")
    return done


def do_tailor(conn, run, settings, job_ids: list[int]) -> str:
    ctx = RunContext(conn, run["id"], settings)
    n = _tailor_ids(conn, ctx, job_ids, settings)
    return f"{n} of {len(job_ids)} resume(s) tailored" + ("" if n == len(job_ids) else " (see log)")


def _analyze_ids(conn, ctx: RunContext, ids: list[int], settings) -> int:
    """Score jobs with the configured engine (built-in works offline; Claude is optional)."""
    if not ids:
        return 0
    done = 0
    for i, jid in enumerate(ids, 1):
        ctx.check_cancel()
        ctx.status("running", f"Analyzing job {i} of {len(ids)}")
        try:
            analysis.analyze_job(conn, jid, log=log.info)
            done += 1
        except Exception as e:  # one bad job must not stop the rest
            log.warning(f"  analysis failed for job {jid}: {e}")
    return done


def do_analyze(conn, run, settings, job_ids: list[int]) -> str:
    ctx = RunContext(conn, run["id"], settings)
    ids = job_ids or repo.unanalyzed_matched_job_ids(conn)
    n = _analyze_ids(conn, ctx, ids, settings)
    return f"{n} of {len(ids)} job(s) analyzed"


def _login_targets(conn, only_key: str | None) -> list[tuple[str, str, str]]:
    """(login_key, label, url) for every enabled site with a login page and every enabled company."""
    out = [(s["key"], s["name"], LOGIN_URLS[s["key"]]) for s in repo.list_sites(conn)
           if s["enabled"] and s["key"] in LOGIN_URLS]
    out += [(f"company_{c['id']}", c["name"], c["careers_url"]) for c in repo.list_companies(conn) if c["enabled"]]
    return [t for t in out if not only_key or t[0] == only_key]


def do_login(conn, run, settings, only_key: str | None = None) -> str:
    """Open login pages in the app's browser. Saved logins are filled in; the rest you do by hand."""
    from . import auth
    from .scrapers.browser import open_browser

    targets = _login_targets(conn, only_key)
    if not targets:
        return "Nothing to log in to (turn sites or companies on first)."
    ctx = RunContext(conn, run["id"], settings)
    msg = "Sign in to each tab in the browser window (saved logins are filled for you), then close the window."
    ctx.status("waiting_user", msg)
    with open_browser(False, int(settings["page_timeout_sec"]), settings["browser_channel"]) as browser:
        pages = browser.pages
        for i, (key, label, url) in enumerate(targets):
            page = pages[0] if i == 0 and pages else browser.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded")
                if auth.credentials(conn, key):
                    ctx.sleep(2)
                    auth.auto_login(ctx, page, key)
            except Exception as e:
                log.warning(f"Could not open {label}: {e}")
        log.info(msg)
        while True:  # wait for the user to close the window
            ctx.sleep(2)
            try:
                if not browser.pages:
                    break
            except Exception:
                break
    return "Browser closed; your logins are saved in browser-profile/."


def do_company_test(conn, run, settings, company_id: int, keyword: str | None) -> str:
    """Try one company's careers site with one keyword and report what was found. Saves nothing."""
    from .scrapers.browser import open_browser
    from .scrapers.registry import company_scraper

    company = repo.get_company(conn, company_id)
    if not company:
        return "Company not found."
    if not keyword:
        kws = [k for p in repo.list_profiles(conn) if p["enabled"] for k in p["keywords"]]
        keyword = kws[0] if kws else "developer"
    ctx = RunContext(conn, run["id"], settings)
    scraper = company_scraper(company)
    profile = {"posted_within": "30d", "job_types": [], "work_modes": [], "experience_levels": []}
    with open_browser(settings["headless"], int(settings["page_timeout_sec"]), settings["browser_channel"]) as browser:
        page = browser.new_page()
        cards = list(scraper.search(ctx, page, profile, keyword, ""))
        for c in cards[:10]:
            log.info(f"  found: {c.title[:70]} | {c.location} | {c.url}")
        if cards:
            d = scraper.fetch_detail(ctx, page, cards[0])
            log.info(f"  first job page: title='{d.title}', company='{d.company}', location='{d.location}', "
                     f"description {len(d.description)} chars")
    status = scraper.status or f"ok: {len(cards)} job links"
    repo.set_company_status(conn, company_id, status)
    return f"{company['name']} with '{keyword}': {status}"


def do_tailor_apply(conn, run, settings) -> str:
    """One-button flow: analyze -> tailor resume -> fill application, stop before submit (Phase 5)."""
    jid = run["job_id"]
    job = repo.get_job(conn, jid)
    if not job:
        return "Job not found."
    ctx = RunContext(conn, run["id"], settings)
    ctx.status("running", "Step 1/3: reading the job description")
    if not job["analyzed_at"]:
        analysis.analyze_job(conn, jid, log=log.info)
        job = repo.get_job(conn, jid)
    a = job["analysis"] or {}
    log.info(f"Score {job['match_score']}. Matched: {', '.join(a.get('matched', [])) or '-'}")
    log.info(f"Gaps (not added to your resume): {', '.join(a.get('missing', [])) or '-'}")
    ctx.status("running", "Step 2/3: tailoring your resume")
    from . import tailor
    report = tailor.tailor_job(conn, jid, settings, log=log.info)
    job = repo.get_job(conn, jid)
    files = Path(job["tailored_docx"]).name + (" + PDF" if job["tailored_pdf"] else "")
    if report.get("fallback"):
        log.warning(f"Honesty check: {report['guard']}. Your base resume was used unchanged.")
    log.info(f"Tailored resume ready: {files}")
    ctx.status("running", "Step 3/3: filling the application (it stops before Submit)")
    return do_apply(conn, run, settings, jid)


def _apply_files(conn, job) -> dict:
    files = {"resume": [p for p in (job.get("tailored_pdf"), job.get("tailored_docx")) if p and Path(p).exists()]}
    if not files["resume"]:
        base = repo.resume_for_job(conn, job["id"])
        if base:
            files["resume"] = [str(paths.RESUMES / base["file_name"])]
    if job.get("cover_note_path") and Path(job["cover_note_path"]).exists():
        files["cover_letter"] = [job["cover_note_path"]]
    if job.get("cover_note"):
        files["cover_text"] = job["cover_note"]
    return files


def do_apply(conn, run, settings, job_id: int | None) -> str:
    """Fill the application in the visible browser, stop before Submit, then wait for the person."""
    from . import apply as apply_mod, applicant
    from .scrapers.browser import open_browser

    jid = job_id or run["job_id"]
    job = repo.get_job(conn, jid)
    if not job:
        return "Job not found."
    if repo.get_application_by_job(conn, jid):
        return "You already applied to this job (see Applications)."
    cap = int(settings.get("daily_apply_cap", 15))
    if repo.applied_today(conn) >= cap:
        return f"Daily limit reached ({cap} applications today). Change it in Settings if you really want more."
    a = applicant.load(settings)
    missing = applicant.missing_basics(a)
    if missing:
        raise ValueError("Fill in My details first (missing: " + ", ".join(missing) + ").")
    settings = {**settings, "_site_label": {"linkedin": "LinkedIn", "indeed": "Indeed", "dice": "Dice",
                                             "naukri": "Naukri"}.get(job["site"], "Company website")}
    files = _apply_files(conn, job)
    ctx = RunContext(conn, run["id"], settings)
    wait_min = int(settings.get("apply_wait_minutes", 30))
    with open_browser(False, int(settings["page_timeout_sec"]), settings["browser_channel"]) as browser:
        page = browser.new_page()
        log.info(f"Opening the application for {job['title']} @ {job['company']}")
        form, report = apply_mod.prepare(ctx, page, job["url"], a, settings, files)
        report.update(job_id=jid, title=job["title"], company=job["company"],
                      resume=Path(files["resume"][0]).name if files.get("resume") else None)
        repo.set_run_payload(conn, run["id"], report)
        log.info(f"  filled {len(report['filled'])} field(s); {len(report['needs_you'])} need you; "
                 f"final button: {report['final_button'] or 'not found'}")
        repo.set_job_status(conn, jid, "Ready to review", "Filled; waiting for you to review and submit")
        if settings.get("notify_on_finish", True):
            from . import notify
            notify.toast(f"Review your application: {job['company']}",
                         f"{len(report['filled'])} fields filled, {len(report['needs_you'])} need you. "
                         "Nothing is sent until you approve.", "/today")
        ctx.status("waiting_user", f"Review the application for {job['company']} in the browser window. "
                                   "Nothing is sent until you submit.")
        channel = "easy_apply" if job.get("apply_type") == "easy_apply" else "company_site"
        deadline = time.monotonic() + wait_min * 60
        outcome = None
        while time.monotonic() < deadline:
            ctx.sleep(2)
            try:
                live = [p for p in browser.pages if not p.is_closed()]
            except Exception:
                live = []
            if not live:
                outcome = "closed"
                break
            form = form if not form.is_closed() else live[-1]
            if apply_mod.confirmed(form):
                outcome = "submitted_by_you"
                break
            cmd = repo.take_command(conn, run["id"])
            if cmd == "submit":
                ctx.status("running", "Submitting (you approved)…")
                ok, msg = apply_mod.submit_application(ctx, form)
                log.info(f"  {msg}")
                if ok:
                    outcome = "submitted_by_app"
                    break
                report["note"] = msg
                repo.set_run_payload(conn, run["id"], report)
                ctx.status("waiting_user", msg)
            elif cmd == "done":
                outcome = "submitted_by_you"
                break
            elif cmd == "refill":
                ctx.status("running", "Filling this page again…")
                r = apply_mod.fill(ctx, form, a, settings, files)
                report["filled"] += r["filled"]
                report["needs_you"] = r["needs_you"]
                hit = apply_mod.find_button(form, apply_mod.FINAL_RX) if apply_mod.has_form(form) else None
                if hit:
                    hit[0].evaluate(apply_mod._HIGHLIGHT_JS, hit[1]["i"])
                    report["final_button"] = hit[1]["text"]
                repo.set_run_payload(conn, run["id"], report)
                ctx.status("waiting_user", "Filled again. Review it in the browser window.")
            elif cmd == "cancel":
                outcome = "cancelled"
                break
    if outcome in ("submitted_by_app", "submitted_by_you"):
        used = files["resume"][0] if files.get("resume") else None
        try:
            repo.mark_applied(conn, jid, applied_on=None, channel=channel, notes="",
                              follow_up_days=int(settings.get("follow_up_days", 7)), resume_file=used)
        except ValueError:
            pass
        return f"Applied to {job['company']} ({'you approved' if outcome == 'submitted_by_app' else 'you submitted'}). Logged in Applications."
    repo.set_job_status(conn, jid, "Tailored" if job.get("tailored_at") else "New", "")
    if outcome == "cancelled":
        return "Cancelled; nothing was submitted."
    if outcome == "closed":
        return "Browser closed; nothing logged. If you did submit, press 'Mark as applied' on the job."
    return f"No answer after {wait_min} minutes; the application was left unsent."


def _notify_finished(conn, kind, trigger, msg, settings, ok: bool) -> None:
    """Desktop notification when a search finishes (or any scheduled run fails)."""
    if not settings.get("notify_on_finish", True) or kind not in ("search",):
        return
    from . import notify

    extra = ""
    due = repo.application_counts(conn)["follow_up_due"]
    if due:
        extra = f" · {due} follow-up(s) due"
    title = "Job Assist: daily search done" if trigger == "schedule" else "Job Assist: search done"
    if not ok:
        title = "Job Assist: search stopped"
    notify.toast(title, msg + extra, "/today" if ok else "/runs")


# ------------------------------------------------------------------ main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="jobassist.runner")
    ap.add_argument("kind", choices=["search", "login", "analyze", "tailor", "apply", "tailor-apply", "company-test"])
    ap.add_argument("--run-id", type=int)
    ap.add_argument("--profile-id", type=int)
    ap.add_argument("--job-id", type=int, action="append", default=[])
    ap.add_argument("--trigger", default="manual", choices=["manual", "schedule"])
    ap.add_argument("--login-key")
    ap.add_argument("--company-id", type=int)
    ap.add_argument("--keyword")
    args = ap.parse_args(argv)
    kind = args.kind.replace("-", "_")

    db.init_db()
    conn = db.connect()
    if args.run_id:
        run_id = args.run_id
    else:
        busy = runs.conflicting_run(conn, runs.USES_BROWSER[kind])
        if busy:
            print(f"Another run (#{busy['id']}, {busy['kind']}) is active; not starting.")
            return 2
        run_id = repo.create_run(conn, kind, profile_id=args.profile_id,
                                 job_id=args.job_id[0] if args.job_id else None,
                                 trigger=args.trigger, uses_browser=runs.USES_BROWSER[kind])
    log_file = str(paths.LOGS / f"run_{run_id}.log")
    _setup_logging(log_file)
    repo.update_run(conn, run_id, status="running", pid=os.getpid(), log_file=log_file)
    run = repo.get_run(conn, run_id)
    settings = load_settings(conn)
    log.info(f"Run #{run_id} ({kind}, {args.trigger}) started")
    t0 = time.monotonic()
    try:
        if kind == "search":
            msg = do_search(conn, run, settings)
        elif kind == "login":
            msg = do_login(conn, run, settings, args.login_key)
        elif kind == "company_test":
            msg = do_company_test(conn, run, settings, args.company_id, args.keyword)
        elif kind == "analyze":
            msg = do_analyze(conn, run, settings, args.job_id)
        elif kind == "tailor":
            msg = do_tailor(conn, run, settings, args.job_id)
        elif kind == "apply":
            msg = do_apply(conn, run, settings, args.job_id[0] if args.job_id else None)
        else:
            msg = do_tailor_apply(conn, run, settings)
        repo.update_run(conn, run_id, status="done", message=msg)
        log.info(f"Done in {time.monotonic() - t0:.0f}s: {msg}")
        _notify_finished(conn, kind, args.trigger, msg, settings, ok=True)
        return 0
    except Cancelled:
        repo.update_run(conn, run_id, status="cancelled", message="Stopped by you")
        log.info("Stopped by you.")
        return 1
    except Exception as e:
        log.error(traceback.format_exc())
        repo.update_run(conn, run_id, status="failed", message=str(e)[:400])
        _notify_finished(conn, kind, args.trigger, str(e)[:200], settings, ok=False)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
