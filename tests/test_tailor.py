from datetime import date
from pathlib import Path

import pytest
from docx import Document

from jobassist import skills, tailor
from jobassist.resume_text import docx_to_text

LIB = skills.library("")
SETTINGS = {"custom_skills": "", "tailor_bold_skills": True, "tailor_key_skills_line": True}


def make_resume(path: Path) -> Path:
    d = Document()
    d.add_paragraph("Priya Sample")
    d.add_paragraph("Dallas, TX | priya@example.com")
    d.add_heading("Summary", level=1)
    d.add_paragraph("Software engineer with internship and full-time experience building web services.")
    d.add_heading("Technical Skills", level=1)
    d.add_paragraph("Languages: Python, JavaScript, Java 17, SQL")
    t = d.add_table(rows=1, cols=2)
    t.cell(0, 0).text = "Frameworks"
    t.cell(0, 1).text = "React, Django, Spring Boot, Hibernate"
    d.add_heading("Experience", level=1)
    d.add_paragraph("Software Engineer, Acme Corp - Jun 2024 - Present")
    d.add_paragraph("Improved the React dashboard load time by 30%.", style="List Bullet")
    d.add_paragraph("Wrote Python scripts for reporting.", style="List Bullet")
    d.add_paragraph("Built Spring Boot microservices with Hibernate and Kafka.", style="List Bullet")
    d.add_paragraph("Software Engineering Intern, Beta LLC - May 2023 - Aug 2023")
    d.add_paragraph("Fixed UI bugs in a React app.", style="List Bullet")
    d.add_paragraph("Added REST APIs in Java for order lookup.", style="List Bullet")
    d.add_heading("Education", level=1)
    d.add_paragraph("MS Computer Science, University of Texas at Dallas, 2022 - 2024")
    d.save(str(path))
    return path


JOB = {"title": "Java Developer", "company": "Acme Bank"}
ANALYSIS = {"matched": ["Java", "Spring Boot", "Hibernate", "REST APIs", "Microservices", "SQL"],
            "missing": ["Kubernetes", "AWS"]}


@pytest.fixture
def base(tmp_path):
    return make_resume(tmp_path / "base.docx")


def bullets(path):
    d = Document(str(path))
    return [p.text for p in d.paragraphs if tailor.is_bullet(p)]


def test_bullets_move_up_within_each_job_only(base, tmp_path):
    out = tmp_path / "out.docx"
    r = tailor.tailor_docx(base, out, JOB, ANALYSIS, SETTINGS)
    b = bullets(out)
    assert b[0].startswith("Built Spring Boot")          # most relevant bullet of job 1 is now first
    assert set(b[:3]) == set(bullets(base)[:3])            # job 1 bullets stayed in job 1
    assert b[3].startswith("Added REST APIs")              # job 2: relevant bullet first
    assert set(b[3:]) == set(bullets(base)[3:])
    assert r["bullets_reordered"] >= 2 and r["guard"] == "ok" and not r["fallback"]


def test_skills_reordered_and_bolded_without_changing_words(base, tmp_path):
    out = tmp_path / "out.docx"
    tailor.tailor_docx(base, out, JOB, ANALYSIS, SETTINGS)
    d = Document(str(out))
    line = next(p for p in d.paragraphs if p.text.startswith("Languages:"))
    assert line.text == "Languages: Java 17, SQL, Python, JavaScript"
    assert {r.text for r in line.runs if r.bold} == {"Java 17", "SQL"}
    cell = d.tables[0].cell(0, 1).text
    assert cell == "Spring Boot, Hibernate, React, Django"
    assert d.tables[0].cell(0, 0).text == "Frameworks"


def test_key_skills_line_only_has_resume_skills(base, tmp_path):
    out = tmp_path / "out.docx"
    r = tailor.tailor_docx(base, out, JOB, {**ANALYSIS, "matched": ANALYSIS["matched"] + ["Kubernetes"]}, SETTINGS)
    assert r["key_skills_line"].startswith(tailor.KEY_SKILLS_LABEL)
    assert "Kubernetes" not in r["key_skills_line"]          # not in the resume -> never claimed
    assert "Microservices" in r["key_skills_line"]            # in resume ("microservices" in a bullet)
    text = docx_to_text(out).splitlines()
    assert text[text.index("Summary") + 2].startswith("Key skills for this role")


def test_no_changes_when_options_off(base, tmp_path):
    out = tmp_path / "out.docx"
    r = tailor.tailor_docx(base, out, JOB, {"matched": [], "missing": []},
                           {**SETTINGS, "tailor_key_skills_line": False})
    assert docx_to_text(out) == docx_to_text(base)
    assert r["bullets_reordered"] == 0


def test_honesty_check_catches_inventions():
    base = "Java developer. Built APIs serving 2M users."
    ok, _ = tailor.honesty_check(base, "Built APIs serving 2M users. Java developer.", LIB, strict_words=True)
    assert ok
    assert not tailor.honesty_check(base, base + " Kubernetes expert.", LIB, strict_words=False)[0]
    assert not tailor.honesty_check(base, base.replace("2M", "5M"), LIB, strict_words=False)[0]
    assert not tailor.honesty_check(base, base + " Great team player.", LIB, strict_words=True)[0]


def test_guard_failure_falls_back_to_base(base, tmp_path, monkeypatch):
    def evil(doc, *a, **k):
        doc.add_paragraph("Expert in Kubernetes and Terraform with 10 years experience.")
    monkeypatch.setattr(tailor, "add_key_skills_line", lambda doc, matched, report: evil(doc))
    out = tmp_path / "out.docx"
    r = tailor.tailor_docx(base, out, JOB, ANALYSIS, SETTINGS)
    assert r["fallback"] and "Kubernetes" in r["guard"]
    assert docx_to_text(out) == docx_to_text(base)


def test_claude_reword_guard():
    orig = "Built Spring Boot microservices with Hibernate and Kafka."
    assert tailor.bullet_ok(orig, "Developed Spring Boot microservices using Hibernate and Kafka.", LIB)[0]
    assert not tailor.bullet_ok(orig, "Built Spring Boot microservices on Kubernetes.", LIB)[0]
    assert not tailor.bullet_ok(orig, "Built 20 Spring Boot microservices with Hibernate and Kafka.", LIB)[0]


def test_split_items_respects_brackets():
    items, sep = tailor._split_items("Spring Boot, AWS (EC2, S3, Lambda), Docker")
    assert items == ["Spring Boot", "AWS (EC2, S3, Lambda)", "Docker"] and sep == ", "


def test_output_name_and_unique_path(tmp_path):
    assert tailor.output_name("Charles Schwab & Co.", "Java Developer (Hybrid)", date(2026, 11, 14)) == \
        "Charles_Schwab_Java_Developer_Hybrid_2026-11-14"
    assert tailor.output_name("Pioneer Consulting Services LLC", "Junior JAVA Developer", date(2026, 11, 14)) == \
        "Pioneer_Consulting_Services_Junior_JAVA_Developer_2026-11-14"
    long = tailor.output_name("International Business Machines Corporation", "Java Developer", date(2026, 11, 14))
    assert long == "International_Business_Java_Developer_2026-11-14"  # cut at a word, not mid-word
    (tmp_path / "A_B_2026-11-14.docx").write_text("x")
    assert tailor.unique_path(tmp_path, "A_B_2026-11-14", ".docx").name == "A_B_2026-11-14_2.docx"


def test_cover_note_is_honest(base):
    note = tailor.cover_note(JOB, ANALYSIS, docx_to_text(base), SETTINGS)
    assert "Java Developer role at Acme Bank" in note
    assert "Kubernetes" not in note and "AWS" not in note       # gaps never claimed
    assert "One example from my experience: Built Spring Boot microservices" in note  # a real work bullet
    assert note.rstrip().endswith("Priya Sample")
