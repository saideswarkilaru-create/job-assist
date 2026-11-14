from datetime import date

from jobassist import resume_insights as ri

TODAY = date(2026, 11, 14)

JAVA = """Priya Sample
TECHNICAL SKILLS
Java 17, Spring Boot, Hibernate, REST APIs, Microservices, Kafka, AWS, Docker, Angular, TypeScript, SQL, Git, JUnit
EXPERIENCE
Software Engineer, Acme Corp — Jun 2024 – Present
- Built Spring Boot microservices on AWS.
Software Engineering Intern, Beta LLC — May 2023 - Aug 2023
Part-time Developer, Gamma — Jan 2024 to Jul 2024
EDUCATION
Master of Science in Computer Science, University of Texas at Dallas — Aug 2022 – May 2024
B.Tech, JNTU — 2015 - 2019
"""

SDET = """SKILLS: Selenium WebDriver, TestNG, Cucumber BDD, Rest Assured, Postman, Java, Jenkins, JIRA, SQL, Page Object
EXPERIENCE
QA Automation Engineer Intern, Delta — 01/2025 - Present"""

SETTINGS = {"years_of_experience": 2, "custom_skills": "", "analysis_engine": "builtin"}


def test_experience_merges_overlaps_and_ignores_education():
    e = ri.estimate_experience(JAVA, TODAY)
    # Jan 2024 - Nov 2026 (merged with the overlapping part-time role) = 35 months, + 4 months internship
    assert e["years"] == round(39 / 12, 1)
    assert e["includes_internships"]
    assert all("University" not in r["line"] and "JNTU" not in r["line"] for r in e["ranges"])


def test_experience_numeric_dates_and_none():
    assert ri.estimate_experience(SDET, TODAY)["years"] == round(23 / 12, 1)
    assert ri.estimate_experience("Skills: Java, SQL", TODAY)["years"] is None


def test_experience_without_headings_skips_degree_lines():
    text = "Acme — Software Engineer — 2021 - 2023\nMS Computer Science, Some University, 2023 - 2025"
    assert ri.estimate_experience(text, TODAY)["years"] == 3.0


def test_plain_words_do_not_look_like_degrees():
    text = "EXPERIENCE\nAcme — Engineer, responsible to be on call — Jan 2022 - Dec 2023\nMS Computer Science — 2024 - 2025"
    assert ri.estimate_experience(text, TODAY)["years"] == 2.0


def test_top_skills_prefers_specific_over_generic():
    names = [s["name"] for s in ri.top_skills("Java. Spring Boot, Spring Boot, Spring Boot. AWS Lambda. Java, Java")]
    assert names.index("Java") < names.index("Spring Boot")
    assert "Spring" not in names  # only appeared inside "Spring Boot"


def test_roles_ranked_by_resume():
    found = {"Java": 3, "Spring Boot": 2, "Microservices": 1, "Hibernate": 1}
    ranked = ri.score_roles(found)
    assert ranked[0]["name"] == "Java Backend Developer" and ranked[0]["confidence"] == 0.6  # 9 of 15 signal points
    assert ranked[-1]["name"] == ri.GENERAL  # general role always listed last
    assert all(r["name"] != "SDET / QA Automation" for r in ranked)  # no core skill -> not suggested


def test_suggestions_for_java_new_grad():
    s = ri.suggest(JAVA, SETTINGS)
    kws = s["suggestions"]["keywords"]
    ticked = [k["value"] for k in kws if k["selected"]]
    assert ticked[:2] == ["Java Developer", "Java Software Engineer"]
    assert 4 <= len(ticked) <= 6
    assert "Software Engineer I" in ticked  # new-grad title for an MS grad
    assert {k["value"] for k in s["suggestions"]["exclude"]} >= {"Senior", "Lead", "Principal"}
    assert s["suggestions"]["must_include"][0]["value"] == "Java"
    assert not s["suggestions"]["must_include"][0]["selected"]  # optional, off by default
    assert s["profile_defaults"] == {"name": "Java Backend Developer", "max_years": 4, "experience_levels": ["Entry", "Mid"]}


def test_suggestions_for_sdet_and_seniority():
    s = ri.suggest(SDET, {**SETTINGS, "years_of_experience": 1})
    assert s["roles"][0]["name"] == "SDET / QA Automation"
    assert "SDET" in [k["value"] for k in s["suggestions"]["keywords"] if k["selected"]]
    mid = ri.suggest(JAVA, {**SETTINGS, "years_of_experience": 5})
    assert "Senior" not in [k["value"] for k in mid["suggestions"]["exclude"]]
    assert not any(k["value"].startswith(("Junior", "Entry")) for k in mid["suggestions"]["keywords"])


def test_existing_profile_terms_not_suggested_again():
    s = ri.suggest(JAVA, SETTINGS, {"keywords": ["java developer"], "exclude": ["Senior"]})
    assert "Java Developer" not in [k["value"] for k in s["suggestions"]["keywords"]]
    assert "Senior" not in [k["value"] for k in s["suggestions"]["exclude"]]


def test_roles_file_uses_known_skill_names():
    from jobassist import skills
    known = {s.name for s in skills.library("")}
    for r in ri.roles():
        unknown = {k for k, _ in r.signals} - known
        assert not unknown, f"{r.name} uses unknown skills: {unknown}"
        assert set(r.core) <= known, r.name
