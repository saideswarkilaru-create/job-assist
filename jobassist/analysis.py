"""JD analysis: which skills the job asks for, which the resume shows, gaps, and a 0-100 score.

Two engines, same output shape:
- builtin (default): offline, deterministic ATS-style matcher (skills library + JD section weights).
- claude (optional): `claude -p` for people who have Claude Code installed.

Gaps ("missing") are shown to the user only. They are never written into a resume.
"""
from __future__ import annotations

from . import claude_cli, jd_parse, repo, skills
from .filters import experience_of
from .settings import load as load_settings

SECTION_WEIGHT = {"required": 1.0, "other": 0.8, "preferred": 0.4}

AUTH_LABEL = {
    "no_sponsorship": "says no visa sponsorship",
    "no_opt": "says no OPT/CPT",
    "usc_only": "US citizens only",
    "usc_gc_only": "US citizens / green card only",
    "clearance": "needs a security clearance",
    "sponsor_friendly": "mentions sponsorship / OPT is OK",
    "w2_only": "W2 only (no C2C)",
}


# ------------------------------------------------------------------ builtin engine
def builtin(job: dict, resume_text: str, settings: dict) -> dict:
    lib = skills.library(settings.get("custom_skills", "") or "")
    meta = skills.by_name(lib)
    desc = job.get("description", "")
    sec = jd_parse.sections(desc)

    # weight of each JD skill = strongest section it appears in x its category weight
    jd_weight: dict[str, float] = {}
    jd_count: dict[str, int] = {}
    parts = ("required", "preferred", "other") if sec["has_headings"] else ("other",)
    for part in parts:
        text = sec[part] if sec["has_headings"] else desc
        for name, n in skills.find(text, lib).items():
            w = SECTION_WEIGHT[part] * meta[name].weight
            jd_weight[name] = max(jd_weight.get(name, 0), w)
            jd_count[name] = jd_count.get(name, 0) + n
    for name, n in skills.find(job.get("title", ""), lib).items():  # title skills are always core
        jd_weight[name] = max(jd_weight.get(name, 0), 1.2 * meta[name].weight)
        jd_count[name] = jd_count.get(name, 0) + n

    resume_skills = skills.find(resume_text, lib)
    order = sorted(jd_weight, key=lambda k: (-jd_weight[k], -jd_count[k], k))
    matched = [s for s in order if s in resume_skills]
    missing = [s for s in order if s not in resume_skills]

    total = sum(jd_weight.values())
    skill_score = 100 * sum(jd_weight[s] for s in matched) / total if total else 50.0

    years_req = jd_parse.years_required(desc)
    cand_years = float(settings.get("years_of_experience") or 0)
    exp_penalty = min(30.0, max(0.0, (years_req - cand_years) * 5)) if years_req else 0.0
    score = round(max(0.0, min(100.0, skill_score - exp_penalty)))

    flags = jd_parse.auth_flags(f"{job.get('title', '')}\n{desc}")
    blockers = jd_parse.auth_blockers(flags, settings.get("work_authorization", ""))
    required = [s for s in order if jd_weight[s] >= 0.8 * meta[s].weight]
    preferred = [s for s in order if s not in required]

    summary = _summary(len(matched), len(order), [s for s in missing if s in required][:3],
                       years_req, cand_years, blockers)
    return {
        "engine": "builtin",
        "score": score,
        "skill_score": round(skill_score),
        "required_skills": required,
        "nice_to_have": preferred,
        "matched": matched,
        "missing": missing,
        "emphasize": matched[:10],
        "years_required": f"{years_req}+ years" if years_req else None,
        "seniority": experience_of(job.get("title", "")),
        "work_authorization": "; ".join(AUTH_LABEL[f] for f in flags) or None,
        "auth_blockers": blockers,
        "employer_type": jd_parse.employer_type(job.get("company", ""), desc, job.get("job_type", "")),
        "summary": summary,
    }


def _summary(n_match, n_total, top_gaps, years_req, cand_years, blockers) -> str:
    if not n_total:
        return ("No known skills found in this description. Add any missing skill names on "
                "Settings > Extra skills so they are recognised next time.")
    parts = [f"Your resume shows {n_match} of the {n_total} skills this job mentions."]
    if top_gaps:
        parts.append("Biggest gaps: " + ", ".join(top_gaps) + ".")
    if years_req and years_req > cand_years:
        parts.append(f"Asks for {years_req}+ years; you have {cand_years:g}.")
    if blockers:
        parts.append("Visa: " + ", ".join(AUTH_LABEL[b] for b in blockers) + ".")
    return " ".join(parts)


# ------------------------------------------------------------------ optional Claude engine
CLAUDE_PROMPT = """You screen job descriptions for one candidate. Compare the JOB with the candidate's RESUME.

Strict rules:
- A skill is "matched" only if the resume clearly shows it (same skill, obvious synonym or version).
- Never assume experience the resume does not state.
- "missing" = JD skills the resume does not show (gaps for the candidate to review).
- "emphasize" = things ALREADY IN THE RESUME to highlight for this job.
- Keep skill names short (1-4 words), as they appear in the JD.
Candidate work authorization: {auth}. Candidate years of experience: {years}.

Score 0-100: required skills most, then years/seniority fit, then nice-to-haves.

Return ONLY JSON:
{{"score": <int>, "required_skills": [], "nice_to_have": [], "matched": [], "missing": [], "emphasize": [],
  "years_required": <string or null>, "seniority": <"Entry"|"Mid"|"Senior"|null>,
  "work_authorization": <string or null>, "summary": <two short sentences>}}

JOB TITLE: {title}
COMPANY: {company}
JOB DESCRIPTION:
{jd}

RESUME:
{resume}
"""


def claude(job: dict, resume_text: str, settings: dict) -> dict:
    prompt = CLAUDE_PROMPT.format(
        auth=settings.get("work_authorization", ""), years=settings.get("years_of_experience", ""),
        title=job["title"], company=job["company"], jd=job["description"][:12000], resume=resume_text[:15000])
    r = claude_cli.ask_json(prompt, model=settings["claude_model_analysis"], timeout=int(settings["claude_timeout_sec"]))
    r["score"] = max(0, min(100, int(r.get("score") or 0)))
    for k in ("required_skills", "nice_to_have", "matched", "missing", "emphasize"):
        r[k] = [str(x).strip() for x in (r.get(k) or []) if str(x).strip()]
    flags = jd_parse.auth_flags(f"{job['title']}\n{job['description']}")  # visa check stays deterministic
    r["auth_blockers"] = jd_parse.auth_blockers(flags, settings.get("work_authorization", ""))
    r["employer_type"] = jd_parse.employer_type(job["company"], job["description"], job.get("job_type", ""))
    r["engine"] = "claude"
    return r


# ------------------------------------------------------------------ entry point
def analyze_job(conn, job_id: int, *, log=print) -> dict:
    job = repo.get_job(conn, job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")
    if not job["description"].strip():
        raise ValueError("This job has no description saved (open it on the site).")
    resume = repo.resume_for_job(conn, job_id)
    if not resume or not resume["text"].strip():
        raise ValueError("Upload a base resume first (Resumes page).")
    s = load_settings(conn)
    engine = s.get("analysis_engine", "builtin")
    if engine == "claude" and not claude_cli.available():
        log("Claude CLI not installed; using the built-in engine.")
        engine = "builtin"
    log(f"Analyzing job {job_id} ({engine}): {job['title']} @ {job['company']} vs '{resume['name']}'")
    result = claude(job, resume["text"], s) if engine == "claude" else builtin(job, resume["text"], s)
    result["resume_name"] = resume["name"]
    repo.save_analysis(conn, job_id, resume["id"], result)
    log(f"  score {result['score']}  matched {len(result['matched'])}  gaps {len(result['missing'])}")
    return result
