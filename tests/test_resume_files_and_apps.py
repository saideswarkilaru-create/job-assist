import csv
import io
from datetime import date
from pathlib import Path

from docx import Document

from jobassist import jd_parse, pdf, repo, resume_check, resume_designs, resume_doc, tailor
from jobassist.resume_text import docx_to_text

from test_tailor import ANALYSIS, JOB, SETTINGS, make_resume

LINKEDIN = "https://www.linkedin.com/in/priya-sample"
GITHUB = "https://github.com/priya/orders"


def linked_resume(path: Path) -> Path:
    make_resume(path)
    d = Document(str(path))
    contact = d.paragraphs[1]
    contact.add_run(" | ")
    resume_designs.add_hyperlink(contact, "linkedin.com/in/priya-sample", LINKEDIN, "Calibri", 11)
    bullet = next(p for p in d.paragraphs if p.text.startswith("Added REST APIs"))
    bullet.add_run(" Code: ")
    resume_designs.add_hyperlink(bullet, "github.com/priya/orders", GITHUB, "Calibri", 11)
    d.save(str(path))
    return path


def links(path: Path) -> set[str]:
    return {h.address for p in Document(str(path)).paragraphs for h in p.hyperlinks}


# ------------------------------------------------------------------ links survive
def test_tailoring_keeps_hyperlinks(tmp_path):
    base = linked_resume(tmp_path / "base.docx")
    out = tmp_path / "out.docx"
    r = tailor.tailor_docx(base, out, JOB, ANALYSIS, SETTINGS)
    assert r["guard"] == "ok" and not r["fallback"]
    assert links(out) == {LINKEDIN, GITHUB}              # still clickable after bullets moved
    moved = next(p for p in Document(str(out)).paragraphs if p.text.startswith("Added REST APIs"))
    assert [h.address for h in moved.hyperlinks] == [GITHUB]


# ------------------------------------------------------------------ parse + designs
def test_parse_structure(tmp_path):
    rd = resume_doc.parse(linked_resume(tmp_path / "r.docx"))
    assert rd.name == "Priya Sample"
    assert any("priya@example.com" in c for c in rd.contact)
    assert {l.url for l in rd.links} == {LINKEDIN, GITHUB}
    assert [s.kind for s in rd.sections] == ["summary", "skills", "experience", "education"]
    exp = rd.section("experience")
    assert [len(e.bullets) for e in exp.entries] == [3, 2]
    assert ("Frameworks", "React, Django, Spring Boot, Hibernate") in rd.section("skills").skills


def test_designs_keep_every_word_and_link(tmp_path):
    base = linked_resume(tmp_path / "r.docx")
    built = resume_designs.build_all(resume_doc.parse(base), docx_to_text(base), tmp_path, "d")
    assert [b["key"] for b in built] == ["classic", "modern", "compact"]
    for b in built:
        assert b["ok"], b
        got = links(Path(b["docx"]))
        assert {LINKEDIN, GITHUB} <= got and "mailto:priya@example.com" in got
        d = Document(b["docx"])
        assert not d.tables and not d.element.body.xpath(".//w:txbxContent")   # ATS-friendly


def test_same_content_detects_drops_and_additions():
    assert resume_designs.same_content("Built APIs in Java", "BUILT apis in java")[0]
    assert not resume_designs.same_content("Built APIs in Java", "Built APIs")[0]
    assert not resume_designs.same_content("Built APIs in Java", "Built APIs in Java and Go")[0]


# ------------------------------------------------------------------ import
def test_pdf_upload_is_converted(tmp_path):
    base = make_resume(tmp_path / "r.docx")
    as_pdf = tmp_path / "r.pdf"
    pdf.docx_to_pdf(base, as_pdf, methods=("browser",))
    out = tmp_path / "converted.docx"
    how = resume_doc.to_docx(as_pdf, out)
    assert how in ("word", "pdf2docx")
    text = docx_to_text(out)
    for phrase in ("Priya Sample", "Spring Boot", "Acme Corp", "University of Texas"):
        assert phrase in text


def test_unsupported_format_rejected(tmp_path):
    f = tmp_path / "r.txt"
    f.write_text("hi")
    try:
        resume_doc.to_docx(f, tmp_path / "x.docx")
        assert False
    except ValueError as e:
        assert "Word" in str(e)


# ------------------------------------------------------------------ resume check
def test_resume_check_findings(tmp_path):
    base = make_resume(tmp_path / "r.docx")
    res = resume_check.check(resume_doc.parse(base))
    titles = " | ".join(i["title"] for i in res["items"])
    assert "Email address" in titles and "No LinkedIn link" in titles and "No phone number" in titles
    assert "1 table(s)" in titles
    assert "Experience section found" in titles
    assert 0 < res["score"] < 100
    linked = resume_check.check(resume_doc.parse(linked_resume(tmp_path / "l.docx")))
    assert "LinkedIn profile link" in " | ".join(i["title"] for i in linked["items"])
    assert linked["score"] > res["score"]


# ------------------------------------------------------------------ naming
def test_file_stem_pattern():
    d = date(2026, 11, 14)
    assert tailor.file_stem("{name}_{role}_Resume", "Priya Sample", "Acme Inc.", "Java Developer", d) == \
        "Priya_Sample_Java_Developer_Resume"
    assert tailor.file_stem("{name} - {company} - {date}", "Priya", "Acme Inc.", "x", d) == "Priya - Acme - 2026-11-14"
    assert tailor.file_stem("Resume/../{name}?", "Priya", "", "", d) == "Resume_.._Priya"   # no path tricks
    assert tailor.file_stem("{name}_Resume", "", "Acme", "Dev", d) == "Resume"


def test_rename_tailored(conn, tmp_path):
    folder = tmp_path / "tailored" / "Acme_Java_2026-11-14"
    folder.mkdir(parents=True)
    (folder / "A.docx").write_text("x")
    (folder / "A.pdf").write_text("x")
    jid = repo.insert_job(conn, {"url": "https://x.com/jobs/1", "site": "dice", "title": "Java"}, None)
    conn.execute("UPDATE jobs SET tailored_docx = ?, tailored_pdf = ? WHERE id = ?",
                 (str(folder / "A.docx"), str(folder / "A.pdf"), jid))
    conn.commit()
    new = tailor.rename_tailored(conn, jid, "Priya Sample Resume.pdf")
    assert Path(new["tailored_docx"]).name == "Priya Sample Resume.docx"
    assert (folder / "Priya Sample Resume.pdf").exists() and not (folder / "A.pdf").exists()
    try:
        tailor.rename_tailored(conn, jid, "   ")
        assert False
    except ValueError:
        pass


# ------------------------------------------------------------------ applications
def _job(conn, n=1):
    j = {"url": f"https://example.com/jobs/{n}", "site": "linkedin", "title": "Java Developer", "company": "Acme",
         "location": "Dallas, TX", "description": "Java"}
    return repo.insert_job(conn, j | jd_parse.inspect(j), None)


def test_application_lifecycle(conn):
    jid = _job(conn)
    a = repo.mark_applied(conn, jid, applied_on="2026-11-01", channel="easy_apply", notes="via LinkedIn",
                          follow_up_days=7, resume_file="C:/x/Priya_Resume.pdf")
    assert a["status"] == "Applied" and a["follow_up_on"] == "2026-11-08"
    assert repo.get_job(conn, jid)["status"] == "Applied"
    try:
        repo.mark_applied(conn, jid, applied_on=None, channel="", notes="", follow_up_days=7, resume_file=None)
        assert False
    except ValueError:
        pass
    items = repo.list_applications(conn)
    assert items[0]["follow_up_due"] == 1 and items[0]["url"] == "https://example.com/jobs/1"
    assert repo.application_counts(conn)["follow_up_due"] == 1

    a = repo.update_application(conn, a["id"], {"status": "Interview", "note": "phone screen Tue"})
    assert a["status"] == "Interview" and a["response_at"]
    assert [h["status"] for h in a["history"]] == ["Applied", "Interview"] and a["history"][-1]["at"]
    a = repo.update_application(conn, a["id"], {"status": "Rejected"})
    assert a["follow_up_on"] is None
    assert repo.list_applications(conn, "active") == []

    repo.delete_application(conn, a["id"])
    assert repo.get_job(conn, jid)["status"] == "New"


def test_applications_csv(conn):
    from jobassist.api import applications_csv

    jid = _job(conn, 2)
    repo.mark_applied(conn, jid, applied_on="2026-11-10", channel="", notes="", follow_up_days=7,
                      resume_file="C:/t/Priya_Sample_Java_Developer_Resume.pdf")
    body = applications_csv(conn).body.decode()
    rows = list(csv.reader(io.StringIO(body)))
    assert rows[0][:3] == ["Applied on", "Status", "Company"]
    assert rows[1][0] == "2026-11-10" and rows[1][6] == "https://example.com/jobs/2"
    assert rows[1][8] == "Priya_Sample_Java_Developer_Resume.pdf"
