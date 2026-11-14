from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

from jobassist.scrapers import careers, dice, indeed, linkedin, naukri
from jobassist.textutil import normalize_url, parse_relative, split_work_mode

P = {"posted_within": "3d", "job_types": ["Contract", "C2C"], "work_modes": ["Remote", "Hybrid"],
     "experience_levels": ["Entry"]}


def qs(url):
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def test_dice_url():
    q = qs(dice.build_search_url(P, "Java developer", "Dallas, TX", 2))
    assert q["q"] == "Java developer" and q["page"] == "2"
    assert q["filters.postedDate"] == "THREE"
    assert q["filters.employmentType"] == "CONTRACTS|THIRD_PARTY"
    assert q["filters.workplaceTypes"] == "Remote|Hybrid"


def test_linkedin_url():
    q = qs(linkedin.build_search_url(P, "SDET", "Remote", 2))
    assert q["location"] == "United States" and q["f_WT"] == "2"
    assert q["f_TPR"] == "r259200" and q["f_JT"] == "C" and q["f_E"] == "2,3" and q["start"] == "25"


def test_linkedin_meta():
    m = linkedin.parse_meta("Plano, TX · 10 hours ago · 75 applicants", "Hybrid | Full-time")
    assert m == {"work_mode": "Hybrid", "job_type": "Full-time", "posted_text": "10 hours ago",
                 "applicants": "75 applicants"}


def test_indeed_url():
    q = qs(indeed.build_search_url({**P, "job_types": ["Contract"]}, "Java", "Dallas, TX", 3))
    assert q == {"q": "Java", "l": "Dallas, TX", "fromage": "3", "jt": "contract", "start": "20"}


def test_naukri_url():
    u = naukri.build_search_url(P, "Java Developer", "Hyderabad, Telangana", 2)
    assert u.startswith("https://www.naukri.com/java-developer-jobs-in-hyderabad-2?")
    assert qs(u)["jobAge"] == "3"


def test_ats_detection_and_search_urls():
    wd = "https://acme.wd5.myworkdayjobs.com/en-US/Careers"
    assert careers.detect_ats(wd) == "workday"
    assert careers.ats_search_url("workday", wd, "java dev") == "https://acme.wd5.myworkdayjobs.com/en-US/Careers?q=java+dev"
    assert careers.detect_ats("https://boards.greenhouse.io/acme") == "greenhouse"
    assert careers.ats_search_url("greenhouse", "https://boards.greenhouse.io/acme", "x") is None
    assert careers.detect_ats("https://www.tcs.com/careers/united-states") is None


def test_normalize_url_dedupes_tracking():
    assert normalize_url("https://www.dice.com/job-detail/abc?searchlink=1") == "https://dice.com/job-detail/abc"
    assert normalize_url("https://www.indeed.com/viewjob?jk=123&from=serp&tk=x") == \
        normalize_url("https://indeed.com/viewjob?tk=x&jk=123")


def test_relative_dates_and_work_mode():
    now = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)
    assert parse_relative("2 hours ago", now).startswith("2026-11-14T10:00")
    assert parse_relative("3d ago", now).startswith("2026-11-11")
    assert parse_relative("30+ days ago", now).startswith("2026-10-15")
    assert parse_relative("Today", now).startswith("2026-11-14")
    assert parse_relative("", now) == ""
    assert split_work_mode("Hybrid work in Southlake, TX") == ("Hybrid", "Southlake, TX")
    assert split_work_mode("Hybrid in Plano, Texas") == ("Hybrid", "Plano, Texas")
    assert split_work_mode("Remote") == ("Remote", "Remote")
    assert split_work_mode("Dallas, TX") == ("", "Dallas, TX")
