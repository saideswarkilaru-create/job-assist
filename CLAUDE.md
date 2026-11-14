# Job Assist: rules for Claude

Local job-application assistant for Windows, built for a non-technical user: a recent MS graduate
job-hunting in the USA. It searches job boards and company career pages with Playwright, screens
every job like a recruiter would (skills, years asked, visa/sponsorship, clearance, staffing vs
direct), scores it against the user's base resume, tailors the resume (Phase 4), and fills
applications up to, never past, the final Submit (Phase 5).

## Non-negotiable rules
1. **Works fully offline, no AI account needed.** The default engine everywhere is built-in and
   deterministic (`skills.py`, `jd_parse.py`, `analysis.builtin`). Claude (`claude -p`) is an
   optional engine only (Settings > Analysis engine). Every feature must work with it turned off.
2. **Nothing hardcoded that the user should control.** Search terms, locations, sources, delays,
   caps, visa status, years, engines and schedule live in the DB and are edited in the UI. Choice
   lists come from `options.py`; settings from `settings.py` SPEC (the UI renders both).
3. **Resume honesty.** Tailoring may only reorder, rephrase and emphasise what is already in the base
   resume. Never invent skills, employers, titles, dates or years. JD skills the resume lacks go in
   the Gaps list (`missing_keywords`) for the user, never into the resume.
4. **Never auto-submit.** Apply-assist stops before the final Submit; the user clicks "Approve & Submit".
5. **Credentials.** Default is manual sign-in in the app's browser profile (`browser-profile/`).
   Opt-in "Save my login" stores the password ONLY in Windows Credential Manager via `keyring`
   (`auth.py`). Never put passwords in the DB, files, logs, API responses or code. Never log them.
   2FA codes and captchas are always left to the user.
6. **No bypassing.** No captcha solving, no stealth/fingerprint tricks, no hidden/private APIs.
   Normal search pages and apply links only. On captcha / login wall / block: `ctx.wait_for_user()`
   (tries a saved login first, then pauses with a banner); if still blocked, the job becomes `Manual`.
7. **Low volume.** Every navigation goes through `RunContext.goto()`; pace with `ctx.delay()`;
   respect `max_detail_pages_per_run`, `max_pages_per_search` and per-profile `max_jobs`.
8. **Easy for a basic user.** Anything that needs installing is handled by `installer/install.ps1`
   (winget for Python; prebuilt UI in releases). Plain-English labels and messages in the UI.
9. Build in phases, keep `pytest` green, and stop after each phase so the user can test.

## Architecture
- `jobassist/` Python package: FastAPI + SQLite + Playwright. All SQL is in `repo.py`.
- `web/` Angular 21 + Angular Material (standalone components, signals, zoneless). FastAPI serves
  the build from `web/dist/web/browser` at http://127.0.0.1:8770.
- Long work (search, login, analysis, Tailor & Apply, company test) runs in a separate process,
  `python -m jobassist.runner <kind>`, tracked in `runs` with a log in `logs/run_<id>.log`. The UI starts
  it via `runs.start()`; Task Scheduler will call the runner directly. One browser run at a time.
- The browser is the user's installed Chrome (Playwright `channel`), falling back to Edge, then
  bundled Chromium. (Bundled Chromium cannot open a visible window on the owner's PC.)
- Data model: `jobs` (one row per normalized URL; JD cached; recruiter signals from
  `jd_parse.inspect`; `fingerprint` + `duplicate_of` link the same job across boards) and `job_hits`
  (each profile's verdict and reason). Duplicates are hidden on Today and never analyzed twice.
- Schema changes: append a new entry to `db.MIGRATIONS`; never edit an applied one.

## Folder structure
```
job-assist/
  Install Job Assist.bat   one-click install / repair (runs installer/install.ps1)
  start.bat                start the app (Desktop shortcut points here)
  run.py                   server launcher: auto-updates libraries, reuses a running instance
  requirements.txt  requirements-dev.txt
  installer/install.ps1    Python via winget, venv, libraries, browser check, shortcuts
  tools/make_release.ps1   builds release/JobAssist.zip for the end user (tests must pass)
  jobassist/
    api.py          FastAPI routes + Angular hosting
    db.py           schema, MIGRATIONS, seed data
    repo.py         all SQL
    settings.py     settings SPEC (candidate, pacing, matching, optional Claude, schedule)
    options.py      choice lists (/api/meta)
    skills.py + data/skills.yaml   skills library and extractor (offline matcher)
    resume_insights.py + data/roles.yaml   resume -> top skills, years (from work dates), roles fit,
                    search-title / exclude / limits suggestions (accept/reject in the UI)
    jd_parse.py     JD sections, years asked, visa/clearance flags, employer type, fingerprint
    analysis.py     builtin (default) and claude (optional) engines, same output shape
    tailor.py       tailored .docx: reorder bullets within each job, skills first + bold, optional
                    key-skills line, optional Claude rewording (bullet guard), honesty_check()
                    on the whole document (fallback = unchanged base), cover note
    resume_doc.py   import (.pdf/.doc -> .docx via Word, else pdf2docx) + parse() resume structure
                    (name, contact, hyperlinks, sections, entries/bullets, skills lines)
    resume_check.py recruiter/ATS checklist with score (suggestions only, never edits)
    resume_designs.py  classic / modern / compact layouts of the SAME content (same_content() check,
                    hyperlinks kept); chosen design saved as a NEW resume (parent_id), original untouched
    applicant.py    My details (config/profile.yaml) + the person's Q&A; no passwords / SSN / DOB
    apply.py        apply-assist: scan fields (all frames), classify the question (question-type rules
                    before contact rules), honest answers only, fill, attach files, Next/Review steps,
                    STOP before final submit (outlined). submit_application() runs only on the
                    person's "Approve & Submit". Confirmation pages detected and logged.
    stats.py        funnel + reply/interview rates by profile, site, keyword; hidden reasons; weekly
    notify.py       Windows toast via PowerShell (no extra installs); click opens the app page
    scheduler.py    Task Scheduler task from XML (StartWhenAvailable, InteractiveToken, LeastPrivilege)
                    + manual_command() shown in Settings; runs scheduled_run.py with pythonw
    pdf.py          .docx -> .pdf: Word (docx2pdf) -> LibreOffice -> mammoth HTML + browser
                    (browser step runs as `python -m jobassist.pdf` in its own process)
    filters.py      profile + candidate screening rules
    engine.py       profile -> sources -> keywords x locations -> screen -> save
    auth.py         login modes; keyring storage; auto sign-in form filler
    runner.py  runs.py   background worker and process tracking
    claude_cli.py   optional `claude -p` wrapper
    resume_text.py  textutil.py
    scrapers/
      base.py       RunContext (goto, pacing, budgets, wait_for_user), Card, JobDetail
      browser.py    persistent browser (Chrome/Edge/Chromium)
      jsonld.py     schema.org JobPosting reader
      dice.py  linkedin.py  indeed.py  naukri.py
      careers.py    company career pages (ATS-aware: Workday, Greenhouse, Lever, iCIMS,
                    SmartRecruiters, Ashby, Oracle) + generic search-box finder + custom sites
      registry.py   source key -> scraper, adapters loader, login URLs
  adapters/          per-company custom scrapers (class Adapter(BaseScraper), __init__(company))
  tests/             pytest suite (parsers, filters, URL builders, storage, keyring safety)
  web/               Angular app (src/app/pages/*, src/app/api.ts)
  config/profile.example.yaml   applicant details template (Phase 5)
  data/ resumes/ tailored/ logs/ browser-profile/ release/   (gitignored)
```

## Commands (PowerShell, project folder)
```
.\Install Job Assist.bat                       # or: powershell -ExecutionPolicy Bypass -File installer\install.ps1
.venv\Scripts\python.exe run.py                # app at http://127.0.0.1:8770
.venv\Scripts\python.exe -m pytest -q          # tests (pip install -r requirements-dev.txt)
.venv\Scripts\python.exe -m jobassist.runner search [--profile-id N]
.venv\Scripts\python.exe -m jobassist.runner analyze
.venv\Scripts\python.exe -m jobassist.runner company-test --company-id N --keyword "Java developer"
cd web; npm run build                          # rebuild screens after UI changes
cd web; npm start                              # UI dev server :4200, proxies /api to :8770
powershell -ExecutionPolicy Bypass -File tools\make_release.ps1   # shareable zip
```

## Adding a source
- Job board: subclass `BaseScraper` in `scrapers/<site>.py` (`search()` yields `Card`s from the
  public search page, `fetch_detail()` returns `JobDetail`; try `jsonld.read_job_posting` first),
  register in `registry._BOARDS`, seed a row in `sites` via a migration, add URL-builder tests.
- Company needing custom handling: write `adapters/<name>.py` with `class Adapter(BaseScraper)`
  taking the company dict; pick it in the company's Handler dropdown.

## Phases
1. Done: structure, schema, UI shell, Profiles, Resumes, Companies & Sites, Settings, Runs, Dice;
   JD analysis and the one-button Tailor & Apply pipeline (analysis live; later steps stubbed).
2. Done: LinkedIn, Indeed, Naukri, company career pages + adapters; offline built-in matcher;
   visa/clearance/years screening; cross-board duplicates; saved logins (Credential Manager);
   one-click installer and release zip; pytest suite.
3. Done: "Suggest keywords" from a resume (Resumes page and profile editor): roles fit, new-grad
   titles, exclude words, max years/levels, years-of-experience estimate; accept/reject; create or
   merge into a profile. Optional Claude adds extra title ideas. Max 6 titles pre-ticked.
   Also done (requested): PDF/.doc resume upload; resume check; resume designs; tailored file
   name pattern (Settings: full_name, tailored_file_pattern; folder tailored/Company_Role_Date/,
   file {name}_{role}_Resume) + rename; Applications tracker (mark applied, statuses with history,
   follow-up due, notes, CSV export) pulled forward from Phase 6.
4. Done: tailored resume (.docx + .pdf in tailored/Company_Role_Date) per job, format-preserving,
   honesty guard; auto-tailor after search for score >= profile min_score; "Tailor resume" button;
   Tailor & Apply runs analyze + tailor; optional cover note; optional Claude rewording.
5. Done: apply-assist. Runner kind `apply` (and step 3 of `tailor_apply`) keeps the browser open on
   the filled form; the UI talks to it through runs.command (submit | done | refill | cancel) and
   runs.payload (review card). Daily cap, follow-up, Applications log. Never auto-submits; sensitive
   fields, consent boxes and per-skill years are always left to the person.
   Tests: tests/test_apply_forms.py drives local sample forms in a real headless browser.
6. Done: Stats page, daily schedule (Settings switch or the exact schtasks command), desktop
   notifications (search finished, application ready for review, follow-ups due). Applications log
   was done earlier. scheduled_run.py also starts the app in the background so the notification opens it.
