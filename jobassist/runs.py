"""Start, track and stop runner processes. Only one browser run at a time (one browser profile)."""
from __future__ import annotations

import subprocess
import sys

import psutil

from . import paths, repo

_KIND_ARG = {"search": "search", "login": "login", "analyze": "analyze", "tailor": "tailor", "apply": "apply",
             "tailor_apply": "tailor-apply", "company_test": "company-test"}
USES_BROWSER = {"search": True, "login": True, "analyze": False, "tailor": False, "apply": True, "tailor_apply": True,
                "company_test": True}


class RunConflict(Exception):
    pass


def reconcile(conn) -> None:
    """Mark runs whose process died (crash, reboot) as failed so they don't block new runs."""
    for r in repo.active_runs(conn):
        if r["status"] == "queued" and not r["pid"]:
            # queued rows get a pid within a second or two; give up on very old ones
            old = conn.execute("SELECT (julianday('now') - julianday(?)) * 86400 > 60", (r["started_at"],)).fetchone()[0]
            if old:
                repo.update_run(conn, r["id"], status="failed", message="Runner never started")
            continue
        if r["pid"] and not psutil.pid_exists(r["pid"]):
            repo.update_run(conn, r["id"], status="failed", message="Runner process ended unexpectedly")


def conflicting_run(conn, uses_browser: bool) -> dict | None:
    reconcile(conn)
    for r in repo.active_runs(conn):
        if r["uses_browser"] and uses_browser:
            return r
        if r["kind"] in ("analyze", "tailor") and not uses_browser:
            return r
    return None


def start(conn, kind: str, *, profile_id=None, job_ids: list[int] | None = None,
          extra: dict[str, str | int] | None = None) -> dict:
    uses_browser = USES_BROWSER[kind]
    busy = conflicting_run(conn, uses_browser)
    if busy:
        what = busy.get("kind")
        raise RunConflict(f"Run #{busy['id']} ({what}) is still active. Wait for it or stop it first.")
    job_ids = job_ids or []
    run_id = repo.create_run(conn, kind, profile_id=profile_id,
                             job_id=job_ids[0] if len(job_ids) == 1 else None, uses_browser=uses_browser)
    cmd = [sys.executable, "-m", "jobassist.runner", _KIND_ARG[kind], "--run-id", str(run_id)]
    if profile_id:
        cmd += ["--profile-id", str(profile_id)]
    for j in job_ids:
        cmd += ["--job-id", str(j)]
    for k, v in (extra or {}).items():
        if v not in (None, ""):
            cmd += [f"--{k.replace('_', '-')}", str(v)]
    paths.ensure_dirs()
    crash_log = open(paths.LOGS / f"run_{run_id}.stderr.log", "w", encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proc = subprocess.Popen(cmd, cwd=str(paths.ROOT), stdout=crash_log, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, creationflags=flags)
    crash_log.close()
    repo.update_run(conn, run_id, pid=proc.pid)
    return repo.get_run(conn, run_id)


def stop(conn, run_id: int) -> None:
    conn.execute("UPDATE runs SET cancel_requested = 1 WHERE id = ?", (run_id,))
    conn.commit()


def read_log(run: dict, tail_lines: int = 400) -> str:
    parts = []
    for name in (run.get("log_file"), str(paths.LOGS / f"run_{run['id']}.stderr.log")):
        if not name:
            continue
        try:
            with open(name, encoding="utf-8", errors="replace") as f:
                text = f.read().strip()
            if text:
                parts.append(text)
        except FileNotFoundError:
            pass
    lines = "\n".join(parts).splitlines()
    return "\n".join(lines[-tail_lines:])
