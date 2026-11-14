"""End to end through the runner with Claude unavailable: the end user's PC has no Claude."""
from pathlib import Path

from jobassist import claude_cli, jd_parse, paths, repo, runner, settings
from jobassist.resume_text import docx_to_text
from jobassist.scrapers.base import RunContext

from test_tailor import make_resume

JD = """Requirements:
- Java and Spring Boot microservices, Hibernate
- SQL
Nice to have: Kubernetes
"""


def test_score_tailor_and_cover_note_without_claude(conn, monkeypatch):
    monkeypatch.setattr(claude_cli, "available", lambda: False)
    paths.RESUMES.mkdir(parents=True, exist_ok=True)
    make_resume(paths.RESUMES / "base.docx")
    rid = repo.create_resume(conn, "Base", "base.docx", "base.docx", docx_to_text(paths.RESUMES / "base.docx"))["id"]
    prof = repo.create_profile(conn, {"name": "P", "keywords": ["java"], "resume_id": rid, "min_score": 10})
    run_id = repo.create_run(conn, "search", profile_id=prof["id"])
    job = {"url": "https://example.com/jobs/1", "site": "dice", "title": "Java Developer", "company": "Acme Bank",
           "location": "Dallas, TX", "description": JD}
    jid = repo.insert_job(conn, job | jd_parse.inspect(job), run_id)
    repo.upsert_hit(conn, jid, prof["id"], run_id, "java", "", "dice", True, "matched")

    s = settings.save(conn, {"analysis_engine": "claude", "make_pdf": False, "cover_note_enabled": True})
    ctx = RunContext(conn, run_id, s)
    assert runner._analyze_ids(conn, ctx, repo.unanalyzed_matched_job_ids(conn, run_id), s) == 1
    j = repo.get_job(conn, jid)
    assert j["analysis"]["engine"] == "builtin"           # fell back from claude, offline
    assert repo.tailor_candidates(conn, run_id) == [jid]  # score >= profile minimum

    assert runner._tailor_ids(conn, ctx, [jid], s) == 1
    j = repo.get_job(conn, jid)
    assert j["status"] == "Tailored"
    docx = Path(j["tailored_docx"])
    # one folder per job (Company_Role_Date); the file carries the candidate's name for the employer
    assert docx.exists() and docx.parent.parent == paths.TAILORED
    assert docx.parent.name.startswith("Acme_Bank_Java_Developer_")
    assert docx.name == "Priya_Sample_Java_Developer_Resume.docx"
    assert j["tailor_report"]["guard"] == "ok"
    assert "Kubernetes" in j["tailor_report"]["gaps"]
    assert "Kubernetes" not in docx_to_text(docx)
    assert "Acme Bank" in j["cover_note"] and Path(j["cover_note_path"]).exists()
    assert repo.tailor_candidates(conn, run_id) == []    # not tailored twice
