from jobassist import auth, jd_parse, repo


def _job(url, site, **kw):
    d = {"url": url, "site": site, "title": "Java Developer", "company": "Charles Schwab",
         "location": "Southlake, TX", "description": "Java Spring. Unable to sponsor."} | kw
    return d | jd_parse.inspect(d)


def test_migrations_and_seed(conn):
    assert conn.execute("PRAGMA user_version").fetchone()[0] >= 2
    keys = {s["key"]: s["enabled"] for s in repo.list_sites(conn)}
    assert keys["linkedin"] and keys["indeed"] and not keys["naukri"]
    assert repo.list_companies(conn)[0]["name"] == "TCS USA"


def test_cross_board_duplicate_is_linked_and_hidden(conn):
    p = repo.create_profile(conn, {"name": "P", "keywords": ["java"]})
    a = repo.insert_job(conn, _job("https://linkedin.com/jobs/view/1", "linkedin"), None)
    b = repo.insert_job(conn, _job("https://indeed.com/viewjob?jk=9", "indeed",
                                   company="Charles Schwab Inc.", location="Hybrid work in Southlake, TX"), None)
    assert repo.get_job(conn, b)["duplicate_of"] == a
    assert repo.get_job(conn, a)["auth_flags"] == ["no_sponsorship"]
    for jid in (a, b):
        repo.upsert_hit(conn, jid, p["id"], None, "java", "", "x", True, "matched")
    listed = repo.list_jobs(conn)
    assert [j["id"] for j in listed] == [a]
    assert listed[0]["also_on"] == "indeed"
    assert repo.unanalyzed_matched_job_ids(conn) == [a]


def test_profile_lists_are_cleaned(conn):
    p = repo.create_profile(conn, {"name": "X", "keywords": [" Java ", "java", "", "Spring Boot"], "max_years": "3"})
    assert p["keywords"] == ["Java", "Spring Boot"] and p["max_years"] == 3


def test_saved_login_keeps_password_out_of_db(conn, fake_keyring):
    auth.save_login(conn, "linkedin", "saved", "me@example.com", "s3cret-pw")
    dump = "\n".join(conn.iterdump())
    assert "s3cret-pw" not in dump
    assert auth.credentials(conn, "linkedin") == ("me@example.com", "s3cret-pw")
    auth.save_login(conn, "linkedin", "manual")
    assert auth.credentials(conn, "linkedin") is None
    assert fake_keyring.store == {}


def test_key_for_url(conn):
    assert auth.key_for_url(conn, "https://www.linkedin.com/login") == "linkedin"
    cid = repo.list_companies(conn)[0]["id"]
    assert auth.key_for_url(conn, "https://www.tcs.com/careers/x") == f"company_{cid}"
