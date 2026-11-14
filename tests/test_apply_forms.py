"""Apply-assist against local sample forms in a real (headless) browser. Nothing leaves this PC."""
from pathlib import Path

import pytest

from jobassist import apply, applicant

SINGLE = """<!doctype html><html><body>
<h1>Apply: Java Developer</h1>
<form id="f" onsubmit="event.preventDefault(); document.body.innerHTML = '<h2>Thank you for applying!</h2>';">
  <label for="fn">First Name *</label><input id="fn" required>
  <label for="ln">Last Name *</label><input id="ln" required>
  <label for="em">Email *</label><input id="em" type="email" required>
  <label for="ph">Phone</label><input id="ph">
  <label for="cv">Resume/CV *</label><input id="cv" type="file" accept=".pdf,.doc,.docx" required>
  <label for="li">LinkedIn Profile</label><input id="li">
  <label for="au">Are you legally authorized to work in the United States? *</label>
  <select id="au" required><option>Select...</option><option>Yes</option><option>No</option></select>
  <fieldset><legend>Will you now or in the future require sponsorship for employment visa status? *</legend>
    <label><input type="radio" name="sp" value="y" required> Yes</label>
    <label><input type="radio" name="sp" value="n"> No</label></fieldset>
  <label for="ky">How many years of experience do you have with Kafka? *</label><input id="ky" required>
  <label for="ss">Social Security Number</label><input id="ss">
  <label for="gd">Gender</label>
  <select id="gd"><option></option><option>Male</option><option>Female</option><option>Decline To Self Identify</option></select>
  <label for="st">State</label><select id="st"><option>Ohio</option><option>Texas</option></select>
  <label for="np">What is your notice period?</label><textarea id="np"></textarea>
  <label><input type="checkbox" id="pp" required> I agree to the privacy policy *</label>
  <button type="submit">Submit Application</button>
</form></body></html>"""

WIZARD = """<!doctype html><html><body>
<div id="s1"><label for="a">First name</label><input id="a">
  <label for="b">Email address</label><input id="b">
  <button onclick="document.getElementById('s1').remove(); document.getElementById('s2').style.display='block'">Next</button></div>
<div id="s2" style="display:none"><label for="c">Mobile phone number</label><input id="c">
  <label for="d">Upload resume</label><input id="d" type="file">
  <button onclick="document.body.innerHTML='<p>Your application was submitted.</p>'">Submit application</button></div>
</body></html>"""


class Ctx:
    s = {"page_timeout_sec": 30}

    def sleep(self, _):
        pass

    def goto(self, page, url):
        page.goto(url)

    def wait_for_user(self, page, kind):
        raise AssertionError(f"unexpected {kind}")


A = applicant.DEFAULTS | {"first_name": "Priya", "last_name": "Sample", "email": "priya@example.com",
                          "phone": "+1 469 555 0100", "linkedin_url": "https://linkedin.com/in/priya",
                          "state": "TX", "requires_sponsorship": "Yes",
                          "answers": [{"question": "notice period", "answer": "2 weeks"}]}
SETTINGS = {"years_of_experience": 2, "custom_skills": ""}


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = None
        for ch in ("chrome", "msedge", None):
            try:
                b = p.chromium.launch(headless=True, **({"channel": ch} if ch else {}))
                break
            except Exception:
                continue
        if b is None:
            pytest.skip("no browser available")
        yield b
        b.close()


@pytest.fixture
def files(tmp_path):
    cv = tmp_path / "Priya_Sample_Java_Developer_Resume.pdf"
    cv.write_bytes(b"%PDF-1.4 test")
    return {"resume": [str(cv)]}


def _page(browser, tmp_path, html, name):
    f = tmp_path / name
    f.write_text(html, encoding="utf-8")
    page = browser.new_page()
    return page, f.as_uri()


def test_single_page_form_filled_honestly_and_not_submitted(browser, tmp_path, files):
    page, url = _page(browser, tmp_path, SINGLE, "single.html")
    form, r = apply.prepare(Ctx(), page, url, A, SETTINGS, files)
    v = lambda sel: page.eval_on_selector(sel, "e => e.value")
    assert (v("#fn"), v("#ln"), v("#em"), v("#ph")) == ("Priya", "Sample", "priya@example.com", "+1 469 555 0100")
    assert v("#li") == "https://linkedin.com/in/priya"
    assert page.eval_on_selector("#au", "e => e.options[e.selectedIndex].text") == "Yes"
    assert page.eval_on_selector("input[name=sp][value=y]", "e => e.checked")          # needs sponsorship: Yes
    assert page.eval_on_selector("#gd", "e => e.options[e.selectedIndex].text") == "Decline To Self Identify"
    assert page.eval_on_selector("#st", "e => e.options[e.selectedIndex].text") == "Texas"   # TX -> Texas
    assert v("#np") == "2 weeks"                                                          # the person's Q&A
    assert page.eval_on_selector("#cv", "e => e.files[0].name") == "Priya_Sample_Java_Developer_Resume.pdf"
    # honesty: never guessed, never ticked, never typed
    assert v("#ky") == "" and v("#ss") == ""
    assert not page.eval_on_selector("#pp", "e => e.checked")
    needs = " | ".join(f"{n['label']}: {n['why']}" for n in r["needs_you"])
    assert "Kafka" in needs and "Social Security" in needs and "privacy policy" in needs
    # stopped before Submit, and the Submit button is outlined for the person
    assert r["final_button"] == "Submit Application"
    assert "Thank you" not in page.inner_text("body")
    assert "solid" in page.eval_on_selector("button[type=submit]", "e => e.style.outline")


def test_approve_and_submit_clicks_and_confirms(browser, tmp_path, files):
    page, url = _page(browser, tmp_path, SINGLE, "single2.html")
    form, r = apply.prepare(Ctx(), page, url, A, SETTINGS, files)
    page.fill("#ky", "1")              # the person answers what the app left for them
    page.check("#pp")
    ok, msg = apply.submit_application(Ctx(), form)
    assert ok and apply.confirmed(form)


def test_wizard_steps_then_stops(browser, tmp_path, files):
    page, url = _page(browser, tmp_path, WIZARD, "wizard.html")
    form, r = apply.prepare(Ctx(), page, url, A, SETTINGS, files)
    assert r["steps"] == 2 and r["final_button"] == "Submit application"
    assert page.eval_on_selector("#c", "e => e.value") == "+1 469 555 0100"
    assert page.eval_on_selector("#d", "e => e.files.length") == 1
    assert "submitted" not in page.inner_text("body")       # outlined, never clicked
    assert page.is_visible("text=Submit application")


def test_existing_answers_are_kept(browser, tmp_path, files):
    html = SINGLE.replace('<input id="em" type="email" required>',
                          '<input id="em" type="email" value="already@site.com" required>')
    page, url = _page(browser, tmp_path, html, "prefilled.html")
    apply.prepare(Ctx(), page, url, A, SETTINGS, files)
    assert page.eval_on_selector("#em", "e => e.value") == "already@site.com"


@pytest.mark.parametrize("opts, ans, want", [
    (["Select...", "Yes", "No"], "No", "No"),
    (["United States of America", "Canada"], "United States", "United States of America"),
    (["I don't wish to answer", "Male"], applicant.DECLINE, "I don't wish to answer"),
    (["Texas", "Ohio"], "Texas", "Texas"),
    (["Red", "Blue"], "Yes", None),
])
def test_choose_option(opts, ans, want):
    assert apply.choose_option(opts, ans) == want


def test_applicant_defaults_survive_partial_save(tmp_path, monkeypatch):
    from jobassist import paths
    monkeypatch.setattr(paths, "CONFIG", tmp_path)
    applicant.save({"first_name": "Priya", "email": "p@example.com"})
    a = applicant.load({"work_authorization": "F-1 OPT / STEM OPT (will need H-1B later)"})
    assert a["authorized_to_work"] == "Yes" and a["country"] == "United States"
    assert a["gender"] == applicant.DECLINE and a["requires_sponsorship"] == "Yes"   # from Settings
    applicant.save({"phone": "+1 469 555 0100"})                                      # partial update
    a = applicant.load()
    assert a["first_name"] == "Priya" and a["phone"] == "+1 469 555 0100"
    assert applicant.missing_basics(a) == ["last name"]
    assert "password" not in (tmp_path / "profile.yaml").read_text().lower().replace("never put passwords", "")


@pytest.mark.parametrize("label, key", [   # real questions seen on a live Greenhouse form
    ("Will you now or in the future require sponsorship for a visa to remain in your current location?", "requires_sponsorship"),
    ("Are you subject to any employment agreements and/or post-employment restrictions with your current employer?", None),
    ("What is your current country of residence?", "country"),
    ("Are you located in India?", None),
    ("Have you previously worked at or consulted for GitLab?", None),
    ("Current location", "location"),
    ("LinkedIn Profile", "linkedin_url"),
])
def test_real_world_question_mapping(label, key):
    assert apply.classify(label) == key
