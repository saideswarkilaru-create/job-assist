import xml.etree.ElementTree as ET

from jobassist import jd_parse, notify, repo, scheduler, stats


def _job(conn, n, site="linkedin", title="Java Developer"):
    j = {"url": f"https://example.com/jobs/{n}", "site": site, "title": title, "company": f"Co{n}",
         "location": "Dallas, TX", "description": "Java"}
    return repo.insert_job(conn, j | jd_parse.inspect(j), None)


def test_funnel_rates_and_breakdowns(conn):
    p = repo.create_profile(conn, {"name": "Java", "keywords": ["java developer"]})
    ids = [_job(conn, i, site="linkedin" if i < 3 else "dice") for i in range(5)]
    for jid in ids[:4]:
        repo.upsert_hit(conn, jid, p["id"], None, "java developer", "", "x", True, "matched")
    repo.upsert_hit(conn, ids[4], p["id"], None, "java developer", "", "x", False, "visa: no sponsorship")
    apps = [repo.mark_applied(conn, jid, applied_on=None, channel="", notes="", follow_up_days=7, resume_file=None)
            for jid in ids[:3]]
    repo.update_application(conn, apps[0]["id"], {"status": "Interview"})
    repo.update_application(conn, apps[0]["id"], {"status": "Rejected"})     # interviewed, then rejected
    repo.update_application(conn, apps[1]["id"], {"status": "Screening"})

    f = {x["step"]: x["count"] for x in stats.funnel(conn)}
    assert f == {"Found": 5, "Matched": 4, "Tailored": 0, "Applied": 3, "Responses": 2, "Interviews": 1, "Offers": 0}
    s = stats.summary(conn, {"daily_apply_cap": 15})
    assert s["response_rate"] == 66.7 and s["interview_rate"] == 33.3 and s["applied_today"] == 3
    prof = stats.by_profile(conn)[0]
    assert (prof["name"], prof["matched"], prof["applied"], prof["interviews"]) == ("Java", 4, 3, 1)
    sites = {r["name"]: r for r in stats.by_site(conn)}
    assert sites["LinkedIn"]["applied"] == 3 and sites["Dice"]["applied"] == 0 and sites["Dice"]["response_rate"] is None
    kw = stats.by_keyword(conn)[0]
    assert kw["name"] == "java developer" and kw["applied"] == 3
    assert stats.hidden_reasons(conn) == [{"reason": "Visa / sponsorship", "count": 1}]
    w = stats.weekly(conn)
    assert len(w) == 12 and w[-1]["applied"] == 3


def test_empty_database_stats(conn):
    s = stats.all_stats(conn, {"daily_apply_cap": 15})
    assert s["summary"]["response_rate"] is None and s["hidden"] == [] and s["scores"]["applied"] is None


def test_task_xml_is_valid_and_catches_up():
    root = ET.fromstring(scheduler.task_xml("07:30").encode("utf-16"))
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    assert root.find(".//t:StartBoundary", ns).text.endswith("T07:30:00")
    assert root.find(".//t:StartWhenAvailable", ns).text == "true"          # runs after sleep
    assert root.find(".//t:LogonType", ns).text == "InteractiveToken"       # only while signed in
    assert root.find(".//t:RunLevel", ns).text == "LeastPrivilege"          # no admin
    assert root.find(".//t:Arguments", ns).text.strip('"').endswith("scheduled_run.py")
    assert scheduler.valid_time("08:00") and not scheduler.valid_time("25:00") and not scheduler.valid_time("8am")
    assert 'schtasks /Create' in scheduler.manual_command("08:00") and "/ST 08:00" in scheduler.manual_command("08:00")


def test_toast_xml_escapes_text():
    x = notify.toast_xml('Acme & Co <Java>', 'Say "hi"', "http://127.0.0.1:8770/today?a=1&b=2")
    root = ET.fromstring(x)
    assert root.get("launch") == "http://127.0.0.1:8770/today?a=1&b=2"
    assert [t.text for t in root.iter("text")] == ["Acme & Co <Java>", 'Say "hi"']
