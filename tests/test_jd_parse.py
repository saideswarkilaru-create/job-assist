import pytest

from jobassist import jd_parse

OPT = "F-1 OPT / STEM OPT (will need H-1B later)"
GC = "Green card / EAD (no sponsorship needed)"
USC = "US citizen"


@pytest.mark.parametrize("text, flag", [
    ("We are unable to sponsor visas at this time.", "no_sponsorship"),
    ("Sponsorship is not available for this role.", "no_sponsorship"),
    ("Must be authorized to work in the US without sponsorship.", "no_sponsorship"),
    ("Will you now or in the future require visa sponsorship?", "no_sponsorship"),
    ("No H1B", "no_sponsorship"),
    ("USC/GC only", "usc_gc_only"),
    ("Green Card holders or US Citizens only please", "usc_gc_only"),
    ("Must be a US citizen.", "usc_only"),
    ("Active Secret clearance required", "clearance"),
    ("TS/SCI with polygraph", "clearance"),
    ("No OPT candidates", "no_opt"),
    ("H1B transfer available. OPT/CPT welcome.", "sponsor_friendly"),
    ("W2 only, no C2C", "w2_only"),
])
def test_auth_flags_detected(text, flag):
    assert flag in jd_parse.auth_flags(text)


def test_sponsor_friendly_dropped_when_also_no_sponsorship():
    flags = jd_parse.auth_flags("Sponsorship available for H1B transfer. We do not sponsor new visas.")
    assert "no_sponsorship" in flags and "sponsor_friendly" not in flags


def test_plain_jd_has_no_flags():
    assert jd_parse.auth_flags("Build Spring Boot services. Great benefits. Equal opportunity employer.") == []


def test_blockers_by_status():
    flags = ["no_sponsorship", "usc_gc_only", "no_opt", "clearance"]
    assert set(jd_parse.auth_blockers(flags, OPT)) == {"no_sponsorship", "usc_gc_only", "no_opt"}
    assert jd_parse.auth_blockers(flags, GC) == []
    assert jd_parse.auth_blockers(["usc_only"], GC) == ["usc_only"]
    assert jd_parse.auth_blockers(["usc_only", "no_sponsorship"], USC) == []


@pytest.mark.parametrize("text, years", [
    ("Requirements:\n- 5+ years of experience with Java\n- 3 years Spring", 5),
    ("3-5 years of professional experience", 3),
    ("Minimum 10 yrs experience in software development", 10),
    ("We have been in business for 25 years. Entry level role, training provided.", None),
    ("Requirements:\n- 2+ years experience\nNice to have:\n- 8+ years experience with Kafka", 2),
])
def test_years_required(text, years):
    assert jd_parse.years_required(text) == years


def test_sections_split_required_and_preferred():
    s = jd_parse.sections("About us\nWe build things.\nRequirements:\n- Java\nNice to have:\n- Kafka\nDocker is a plus")
    assert "Java" in s["required"]
    assert "Kafka" in s["preferred"] and "Docker" in s["preferred"]
    assert s["has_headings"]


def test_employer_type():
    assert jd_parse.employer_type("Acme Corp", "Our client is looking for a Java developer") == "staffing"
    assert jd_parse.employer_type("Global Staffing Inc", "Java developer") == "staffing"
    assert jd_parse.employer_type("Charles Schwab", "Join our engineering team") == "direct"


def test_fingerprint_matches_same_job_across_boards():
    a = jd_parse.fingerprint("Charles Schwab Inc.", "Java Developer (Hybrid)", "Hybrid work in Southlake, TX")
    b = jd_parse.fingerprint("Charles Schwab", "Java Developer", "Southlake, TX, US")
    c = jd_parse.fingerprint("Charles Schwab", "Senior Java Developer", "Southlake, TX")
    assert a == b != c
