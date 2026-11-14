# Job Assist

Your personal job-hunt helper for Windows. It searches **LinkedIn, Indeed, Dice** and **company
career pages** for you, throws out jobs that don't fit (visa, clearance, too many years asked),
scores the rest against your resume, and shows exactly which skills you match and which are missing.

It runs on your own computer. No account, subscription or AI service is needed.

---

## Install (one time, about 5–10 minutes)

### Easiest: one line in PowerShell (recommended)
1. Click **Start**, type **PowerShell**, open **Windows PowerShell**.
2. Paste this line (right-click pastes) and press **Enter**:
   ```
   irm https://raw.githubusercontent.com/saideswarkilaru-create/job-assist/main/get-jobassist.ps1 | iex
   ```
3. Wait until it says **All set!**, then press **Y** to start.

It downloads the latest release, unblocks it (so Windows doesn't silently block the files), extracts it to
`Documents\JobAssist`, installs whatever is missing (Python and the app's parts) and puts a **Job Assist**
icon on your Desktop. Run the same line again later to **update**; your data is kept.
If Windows asks *"Do you want to allow this app to make changes?"*, choose **Yes**.

### Or: from the zip
1. Download **JobAssist.zip** from the [latest release](https://github.com/saideswarkilaru-create/job-assist/releases/latest)
   (not *Code → Download ZIP*, which is the source code).
2. Right-click the zip → **Properties** → tick **Unblock** → **OK**. Then right-click → **Extract All…**.
3. Open the extracted **JobAssist** folder and double-click **`Install Job Assist.bat`**.

If a window flashes and closes, or nothing happens, Windows blocked the file: use the one-line method above.
If anything ever looks broken, run the install again; it repairs itself. Problems are explained on screen
and saved to `install-log.txt` in the JobAssist folder.

## Start the app

Double-click **Job Assist** on your Desktop. Your web browser opens the app.
A small black window also opens (minimized); **keep it open** while you use the app and close it when you're done.

---

## First-time setup inside the app (10 minutes)

### 1. Settings → Candidate
- **Your work authorization**: e.g. *F-1 OPT / STEM OPT*. This decides which jobs are hidden.
- **Your years of professional experience**.
- Leave *"Hide jobs that rule out my visa status"* and *"Hide jobs that require a security clearance"* **on**.
- Press **Save settings**.

### 2. Resumes
Upload your resume as a **Word file (.docx / .doc) or a PDF**. PDFs are converted to Word once so they
can be tailored; your original file is kept. You can upload several (e.g. Java, QA/SDET, Angular).

- **Check** gives your resume a score and a list of fixes and tips, the things recruiters and
  applicant-tracking systems look for (contact details, LinkedIn link, length, results with numbers,
  tables or text boxes that ATS can't read…). It only suggests; it never changes your file.
- **Designs** shows your resume in three clean layouts (Classic, Modern, Compact) with a preview of each.
  The words are exactly yours, and links (email, LinkedIn, GitHub) stay clickable. Pick one, give it a
  name, and it's saved as a new resume. Your original stays as it was.
Each one shows its top skills and roughly how many years of work experience its dates add up to.

**Not sure what to search for?** Press **Suggest keywords** next to a resume. The app reads it and suggests:
- the **roles you fit** (e.g. *Java Backend Developer 83%*),
- **job titles to search**, including new-grad titles like *Software Engineer I*. About 6 are ticked; tick or untick any,
- **words to exclude** (e.g. *Senior, Lead*) and a sensible *max years asked*.

Then choose **Create a new profile** or **Add to profile**. You can also press **Suggest from my resume**
while editing a profile.

### 3. Profiles → New profile
A profile is one saved search, e.g. *"Java – Texas"*.
- **Search keywords**: type each and press Enter (e.g. `Java developer`, `Software engineer`).
- **Exclude**: e.g. `Senior`, `Lead`, `Principal`, `Clearance`.
- **Locations**: type each and press Enter (e.g. `Dallas, TX`, `Remote`).
- **Posted within**: *Last 24 hours* is best. Applying early matters.
- **Skip jobs asking for more than (years)**: for a new grad, **3**.
- **Sites**: LinkedIn, Indeed, Dice (and *Company career pages* if you added companies).
- Press **Save & run now**.

A browser window opens and searches slowly, like a person. You can keep using your computer.

### 4. Today
Your matching jobs, best first. Click a job title to see:
- **Fit score** (0–100) against your resume,
- **Skills you match** (green) and **Gaps** (amber): skills the job wants that your resume doesn't show.
  Gaps are for you to read; they are **never** added to your resume,
- the full job description.

Badges on each job:

| Badge | Meaning |
|---|---|
| **No sponsorship / USC-GC only / US citizens only / No OPT** | The job rules out your visa status (normally hidden) |
| **Sponsor / OPT OK** | The job mentions sponsorship, H-1B transfer or OPT/CPT welcome |
| **5+ yrs** | Minimum years of experience asked |
| **Staffing / vendor** | Posted by a staffing agency for a client |
| **Easy Apply** | You can apply inside LinkedIn / Indeed |
| **75 applicants** | How many applied already (earlier is better) |
| **Also on indeed** | Same job found on several sites; you see it once |

Turn on **Show filtered-out** to see the jobs that were hidden, and why.

### 5. Tailored resumes
For every job that scores at least your profile's **minimum match score**, the app makes a copy of
your resume for that job (you can also press **Tailor resume** on any job). It:
- moves the bullets that matter for this job to the **top of each job** (they never move between jobs),
- puts this job's skills **first and in bold** in your Skills section,
- adds one line under your summary: *"Key skills for this role: …"*, only skills already in your resume.

It **never adds anything you didn't write**. After every tailoring, an honesty check compares the
new file with your original; if anything new appeared (a skill, a number), the app uses your original
resume instead and tells you. Skills the job wants that you don't have are listed as **Gaps** for you.

Each job gets its own folder in `tailored`, named `Company_Role_Date`. Inside it, the files carry the
name the employer will see, by default `Your_Name_Role_Resume.docx` and `.pdf`. Change the pattern in
**Settings → File name for tailored resumes** (a live example shows the result), or type a different name
for one job and press **Rename**. PDFs are made with Microsoft Word if you have it, otherwise with the
app's built-in converter. Open the job on **Today** to download them.
Turn on **Settings → Write a short cover note per job** for a ready-to-paste cover note.
**Tailor & Apply** does it all in one click (applying itself arrives in Phase 5).

### 6. Applying (the app fills the form; you submit)
First fill in **My details** once: name, contact, links, education, work authorization, and your
answers to common questions (e.g. *notice period → 2 weeks*). It's stored only on your computer.

Then on **Today**, open a job and press **Fill the application for me** (or **Tailor & Apply** to score,
tailor and fill in one go). The app's browser window opens the application, fills what it can answer
honestly, attaches your tailored resume, clicks through *Next / Continue / Review*, and **stops before
the final Submit**, which it outlines in red. A review card appears at the top of the app:
- **Filled by the app**: every answer it typed, and where it came from.
- **Needs you**: questions it won't guess, such as years with a specific skill, essay questions,
  company-specific yes/no questions, SSN or date of birth, and terms or consent boxes.

Answer those in the browser window, check everything, then either press the site's own Submit button
(the app notices and logs it) or press **Approve & Submit** in the app. Nothing is ever sent without
that last click from you. **Cancel** closes it without applying. Applying is limited to
**Settings → Max applications per day** (15 by default).

Sites that need you to sign in first (LinkedIn Easy Apply, Indeed, Dice, Workday portals) pause and
ask you to sign in in the window; see *Signing in to job sites*.

### 7. Applications
After you apply, open the job on **Today** and press **Mark as applied** (pick the date and how you applied).
The **Applications** page then shows every application with:
- its **status**: Applied → Screening → Interview → Offer / Rejected / No response / Withdrawn
  (change it as you hear back; the history is kept),
- a **follow-up date** (7 days by default; overdue ones are highlighted),
- the **job link**, the exact **resume you sent**, and your notes,
- **Export CSV** for a spreadsheet of everything.

---

### 8. Stats
**Stats** shows what is working: your funnel (found, matched, tailored, applied, replies, interviews,
offers), reply and interview rates **per profile, per site and per search word**, why jobs were hidden,
applications per week, and whether higher match scores lead to more interviews. Use it every week or
two to drop search words that never get replies.

### 9. Daily search and notifications
**Settings → Daily search**: switch it on and pick a time. Windows then runs all your enabled profiles
every day, even if the app isn't open, and catches up after the laptop wakes if it was asleep. You get
a desktop notification when it finishes ("6 matched, 3 resumes tailored · 2 follow-ups due"); click it
to open the app. You also get one when an application is filled and waiting for your review.
Press **Send a test notification** to check they show up. Prefer to do it yourself? **Show the exact
Task Scheduler command** gives you the one-line `schtasks` command to paste into PowerShell.

## Signing in to job sites

Go to **Companies & Sites → Sign-in**. For each site choose:

- **I'll log in myself** (recommended). Press **Log in now**, sign in in the window that opens, then close it.
  You stay signed in for weeks.
- **Save my login**. Type your email and password once and press **Save**. The app signs in for you when a
  site asks. Your password is kept in **Windows Credential Manager** (Windows' own encrypted password
  store), not in the app's files. If the site sends you a code or shows a "verify you're human" check,
  the app pauses and asks you to do that part.

You can search LinkedIn, Indeed and Dice without signing in. Signing in helps when a site starts
asking for it, and it will be needed for applying (Phase 5).

## When the app needs you

If a site shows a **captcha** or a **login page**, a yellow bar appears at the top of the app.
Handle it in the browser window; the search continues by itself. The app never solves captchas.

**Indeed** in particular often shows *"Just a moment… Verifying you are human"*. Click the checkbox
once in the app's browser window; Indeed then remembers that browser for a while.

## Company career pages

**Companies & Sites → Add a company**: name and careers page link. Then press **Test** to see whether
the app can find jobs there. Big hiring systems (Workday, Greenhouse, Lever, iCIMS, SmartRecruiters,
Ashby, Oracle) work automatically. Some company portals (for example TCS iBegin) need you to sign
in first: use **Log in now** on the Sign-in list.

## Settings worth knowing

- **Min / Max wait between page actions**: higher is slower and safer for your accounts.
- **Max job pages opened per run**: a hard limit per search.
- **Extra skills to recognise**: add skills the matcher doesn't know yet, e.g. `Guidewire: policycenter`.
- **Analysis engine**: *builtin* works offline. *claude* is optional, only if Claude Code is installed.

## Where your things are

| Folder | What's inside |
|---|---|
| `resumes\` | your uploaded resumes |
| `tailored\` | tailored resumes (Phase 4) |
| `data\jobassist.db` | jobs, profiles, history |
| `logs\` | a log of every search (also on **Runs & logs**) |
| `browser-profile\` | the app's own browser profile, where your site sign-ins are kept |

To start completely fresh: close the app and delete the `data` folder.

## Troubleshooting

| Problem | Fix |
|---|---|
| Nothing opens when I start | Run `Install Job Assist.bat` again |
| Browser window doesn't open | Settings → Browser to drive → try `msedge` |
| A site keeps asking to log in | Companies & Sites → Sign-in → **Log in now** |
| A company says "no job search box found" | Sign in to it, press **Test** again, or ask for an adapter |
| Page says "UI not built yet" | Use the release zip, or run `cd web` then `npm run build` |

---

## For the developer

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q                       # tests
.venv\Scripts\python.exe run.py                             # app on http://127.0.0.1:8770
cd web; npm start                                           # UI dev server with live reload (:4200)
powershell -ExecutionPolicy Bypass -File tools\make_release.ps1   # builds release\JobAssist.zip
```

Rules, architecture and folder layout are in `CLAUDE.md`.

## Build phases

1. ✅ Profiles, Resumes, Settings, Runs, Dice, JD analysis, Tailor & Apply button
2. ✅ LinkedIn, Indeed, Naukri, company career pages, offline matcher, visa/years screening,
   duplicate detection, saved logins, one-click installer
3. ✅ Keyword and job-title suggestions from your resume
4. ✅ Tailored resume (.docx + .pdf) and cover notes
5. ✅ Apply-assist: fills the application and stops before Submit; you click Approve & Submit
6. ✅ Applications log, Stats, daily schedule, desktop notifications
