from jobassist import analysis, filters, skills

LIB = skills.library("")


def names(text):
    return set(skills.find(text, LIB))


def test_aliases_and_symbols():
    found = names("Strong C++, C#, .NET Core and ASP.NET; SpringBoot microservices; RESTful APIs; k8s")
    assert {"C++", "C#", ".NET", "ASP.NET", "Spring Boot", "Microservices", "REST APIs", "Kubernetes"} <= found


def test_no_false_positives():
    found = names("Clearance: TS/SCI. Please rest assured. Javascript only. The rest of the team.")
    assert "TypeScript" not in found          # "TS" must not mean TypeScript
    assert "Java" not in found                 # "Javascript" is not Java
    assert "REST APIs" not in found            # lowercase "rest" is plain English


def test_custom_skills():
    lib = skills.library("Guidewire PolicyCenter: policycenter, gw pc")
    assert "Guidewire PolicyCenter" in skills.find("Experience with PolicyCenter config", lib)


JD = """Requirements:
- 5+ years of experience with Java and Spring Boot
- Kafka, Docker, Kubernetes
Nice to have:
- Angular
We are unable to sponsor visas.
"""
SETTINGS = {"work_authorization": "F-1 OPT / STEM OPT (will need H-1B later)", "years_of_experience": 2,
            "custom_skills": ""}


def test_builtin_analysis_shape_and_honesty():
    job = {"title": "Java Developer", "company": "Acme", "description": JD, "location": "Dallas, TX"}
    r = analysis.builtin(job, "Java 17, Spring Boot, Docker, JUnit", SETTINGS)
    assert {"Java", "Spring Boot", "Docker"} <= set(r["matched"])
    assert {"Apache Kafka", "Kubernetes", "Angular"} <= set(r["missing"])
    assert "Angular" in r["nice_to_have"] and "Angular" not in r["required_skills"]
    assert r["years_required"] == "5+ years"
    assert r["auth_blockers"] == ["no_sponsorship"]
    assert 0 <= r["score"] < r["skill_score"]   # experience gap lowers the score
    assert not set(r["matched"]) & set(r["missing"])


PROFILE = {"exclude": ["Clearance required"], "must_include": ["Java"], "must_include_mode": "all",
           "experience_levels": ["Entry", "Mid"], "work_modes": [], "posted_within": "30d", "max_years": 3}


def job(**kw):
    base = {"title": "Java Developer", "company": "Acme", "description": "Java and Spring", "auth_flags": [],
            "years_required": None, "posted_at": ""}
    return {**base, **kw}


def test_filters_candidate_rules():
    cand = {**SETTINGS, "hide_auth_blocked": True, "hide_clearance": True}
    assert filters.evaluate(PROFILE, job(), cand) == (True, "matched")
    assert not filters.evaluate(PROFILE, job(auth_flags=["no_sponsorship"]), cand)[0]
    assert filters.evaluate(PROFILE, job(auth_flags=["no_sponsorship"]), {**cand, "hide_auth_blocked": False})[0]
    assert not filters.evaluate(PROFILE, job(auth_flags=["clearance"]), cand)[0]
    assert "5+ years" in filters.evaluate(PROFILE, job(years_required=5), cand)[1]
    assert filters.evaluate(PROFILE, job(title="Senior Java Developer"), cand)[1] == "looks Senior-level"
    assert filters.evaluate(PROFILE, job(title="Python Developer", description="Python only"), cand)[1] \
        == "missing must-include: Java"


def test_title_exclude_precheck():
    assert filters.title_excluded({"exclude": ["Senior Architect"]}, "Senior Architect - Java")
    assert not filters.title_excluded({"exclude": ["Senior Architect"]}, "Java Developer")
