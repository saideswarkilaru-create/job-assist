"""Deterministic job-description parsing (no AI, works offline).

- sections():         split a JD into required / preferred / other text
- years_required():   minimum years of experience the JD asks for
- auth_flags():       visa / citizenship / clearance language
- employer_type():    direct employer vs staffing / vendor posting
- fingerprint():      company+title+city key to spot one job posted on several boards
- inspect():          all of the above for one job, stored on the jobs row
"""
from __future__ import annotations

import re

# ------------------------------------------------------------------ sections
_REQ_HEAD = re.compile(
    r"^(?:[\W_]*)(?:basic |minimum |required |technical |key |core |must[- ]have )?"
    r"(?:requirements?|qualifications?|skills(?: required| & experience| and experience)?|must[- ]haves?|"
    r"what you(?:'ll)? (?:need|bring|have)|who you are|you have|experience required|required skills|"
    r"skills required|mandatory skills|primary skills|technical skills|job requirements)\b", re.I)
_PREF_HEAD = re.compile(
    r"^(?:[\W_]*)(?:preferred|nice[- ]to[- ]haves?|bonus(?: points)?|good[- ]to[- ]have|pluses|desired|"
    r"additional (?:qualifications|skills)|secondary skills|preferred (?:qualifications|skills))\b", re.I)
_OTHER_HEAD = re.compile(
    r"^(?:[\W_]*)(?:responsibilities|key responsibilities|what you(?:'ll| will) do|duties|about (?:us|the role|the team|the company)|"
    r"benefits|perks|compensation|salary|pay|job description|role overview|overview|summary|why join)\b", re.I)
_PREF_INLINE = re.compile(r"\b(nice to have|is a plus|are a plus|a plus|preferred|bonus|desirable|good to have)\b", re.I)


def sections(text: str) -> dict[str, str]:
    """Return {'required': str, 'preferred': str, 'other': str, 'has_headings': bool}."""
    out = {"required": [], "preferred": [], "other": []}
    current, headings = "other", 0
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        short = len(line) <= 80
        if short and _PREF_HEAD.search(line):
            current, headings = "preferred", headings + 1
        elif short and _REQ_HEAD.search(line):
            current, headings = "required", headings + 1
        elif short and _OTHER_HEAD.search(line):
            current, headings = "other", headings + 1
        target = "preferred" if (current != "preferred" and _PREF_INLINE.search(line)) else current
        out[target].append(line)
    return {k: "\n".join(v) for k, v in out.items()} | {"has_headings": headings > 0}


# ------------------------------------------------------------------ years
_YEARS = re.compile(
    r"(?<![\d.])(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*(\d{1,2})\s*\+?\s*)?(?:years?|yrs?)\b", re.I)
_EXP_CONTEXT = re.compile(r"experience|exp\b|hands[- ]on|working|developing|professional|industry", re.I)
_NOT_EXP = re.compile(r"years? old|years? in business|years? of (?:history|service|excellence)|\bage\b", re.I)


def years_required(text: str) -> int | None:
    """Largest 'minimum years' stated in the required part of a JD (e.g. '5+ years Java' -> 5)."""
    sec = sections(text)
    body = sec["required"] + "\n" + sec["other"] if sec["has_headings"] else text
    found = []
    for m in _YEARS.finditer(body or ""):
        lo = int(m.group(1))
        if lo == 0 or lo > 25:
            continue
        window = body[max(0, m.start() - 60): m.end() + 60]
        if _NOT_EXP.search(window) or not _EXP_CONTEXT.search(window):
            continue
        found.append(lo)
    return max(found) if found else None


# ------------------------------------------------------------------ visa / clearance
_NO_SPONSOR = [
    r"\b(?:no|not|unable to|cannot|can ?not|can't|won't|will not|does not|do not|don't|doesn't|not able to)\b[^.\n]{0,40}\bsponsor",
    r"sponsorship (?:is )?(?:not |un)(?:available|provided|offered|possible)",
    r"without (?:the )?(?:need for |requiring )?(?:current or future |now or future )?(?:visa |employer |employment |h-?1b )?sponsorship",
    r"not eligible for (?:visa |employment )?sponsorship",
    r"(?:now or in the future|currently or in the future)[^.\n]{0,60}sponsor",
    r"\bno (?:visa|h-?1b|h1) (?:sponsorship|transfers?|candidates)",
    r"\bno h-?1b?s?\b",
]
_NO_OPT = [r"\bno (?:opt|cpt|ead|stem opt)\b", r"\b(?:opt|cpt)(?: candidates)? (?:are )?not (?:accepted|eligible|considered)"]
_USC_GC_ONLY = [
    r"\b(?:usc|us citizens?|u\.s\. citizens?)\s*(?:/|,|or|and|&)\s*(?:gc|green card)(?: holders?)?\b[^.\n]{0,25}\bonly\b",
    r"\b(?:gc|green card)(?: holders?)?\s*(?:/|,|or|and|&)\s*(?:usc|us citizens?|u\.s\. citizens?)\b[^.\n]{0,25}\bonly\b",
    r"\bonly\s+(?:usc|us citizens?)\s*(?:/|,|or|and|&)\s*(?:gc|green card)",
    r"\b(?:usc|gc)\s*/\s*(?:gc|usc)\b",
]
_USC_ONLY = [
    r"\b(?:us|u\.s\.)\s+citizens?(?:hip)?\s+(?:only|is required|required)\b",
    r"\bmust be (?:a )?(?:us|u\.s\.|united states) citizen",
    r"\bonly\s+(?:us|u\.s\.)\s+citizens?\b",
    r"\busc only\b",
]
_CLEARANCE = [
    r"\b(?:secret|top secret|ts/sci|ts-sci|public trust|dod|doe|security|active|government)\s+clearance",
    r"\bclearance (?:is )?required\b",
    r"\bts\s*/\s*sci\b",
    r"\b(?:able|ability) to obtain (?:and maintain )?(?:a |an )?(?:security |secret |government )?clearance",
]
_SPONSOR_OK = [
    r"(?:visa |h-?1b )?sponsorship (?:is )?(?:available|provided|offered)",
    r"\bwill sponsor\b", r"\bwilling to sponsor\b",
    r"\bh-?1b (?:transfer|sponsorship)s? (?:available|welcome|accepted|ok|considered)",
    r"\b(?:opt|cpt|stem opt|ead)(?:\s*/\s*(?:opt|cpt|ead|h-?1b|gc|usc))*\s*(?:candidates )?(?:welcome|accepted|considered|ok|eligible)\b",
]
_W2_ONLY = [r"\bno c2c\b", r"\bno corp[- ]to[- ]corp\b", r"\bw-?2 only\b", r"\bonly w-?2\b", r"\bno third[- ]party\b"]


def _any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)


def auth_flags(text: str) -> list[str]:
    """Flags: no_sponsorship, no_opt, usc_only, usc_gc_only, clearance, sponsor_friendly, w2_only."""
    t = text or ""
    flags = []
    if _any(_NO_SPONSOR, t):
        flags.append("no_sponsorship")
    if _any(_NO_OPT, t):
        flags.append("no_opt")
    if _any(_USC_GC_ONLY, t):
        flags.append("usc_gc_only")
    elif _any(_USC_ONLY, t):
        flags.append("usc_only")
    if _any(_CLEARANCE, t):
        flags.append("clearance")
    if _any(_SPONSOR_OK, t) and "no_sponsorship" not in flags:
        flags.append("sponsor_friendly")
    if _any(_W2_ONLY, t):
        flags.append("w2_only")
    return flags


def auth_blockers(flags: list[str], work_authorization: str) -> list[str]:
    """Which flags rule this candidate out, given their work authorization (Settings)."""
    wa = (work_authorization or "").lower()
    if "citizen" in wa:
        return []
    if "green card" in wa:
        return [f for f in flags if f == "usc_only"]
    blocking = {"no_sponsorship", "usc_only", "usc_gc_only"}
    if "opt" in wa:
        blocking.add("no_opt")
    return [f for f in flags if f in blocking]


# ------------------------------------------------------------------ employer type
_STAFFING_TEXT = re.compile(
    r"\b(?:our|my) client\b|on behalf of (?:our|a|one of our) clients?|\bend[- ]client\b|implementation partner|"
    r"\bprime vendor\b|\bw-?2\s*/\s*c2c\b|\bc2c\b|corp[- ]to[- ]corp|\b1099\b|\bthird[- ]party\b|contract to hire|\bc2h\b", re.I)
_STAFFING_NAME = re.compile(r"\b(?:staffing|recruit\w*|talent|consultancy|manpower|workforce|placement)\b", re.I)


def employer_type(company: str, text: str, job_type: str = "") -> str:
    if _STAFFING_NAME.search(company or "") or _STAFFING_TEXT.search(text or "") or "third party" in (job_type or "").lower():
        return "staffing"
    return "direct"


# ------------------------------------------------------------------ duplicates across boards
_LEGAL = re.compile(r"\b(?:inc|llc|ltd|limited|corp|corporation|co|company|plc|lp|llp|gmbh|pvt|private)\b\.?", re.I)


def _norm(s: str) -> str:
    s = re.sub(r"[\(\[\{].*?[\)\]\}]", " ", (s or "").lower())
    s = _LEGAL.sub(" ", s)
    return re.sub(r"[^a-z0-9+#]+", " ", s).strip()


def fingerprint(company: str, title: str, location: str) -> str:
    city = re.split(r"[,;/•|]", (location or "").lower().replace("hybrid work in", "").replace("remote in", ""))[0]
    return f"{_norm(company)}|{_norm(title)}|{_norm(city)}"


# ------------------------------------------------------------------ all-in-one
def inspect(job: dict) -> dict:
    text = f"{job.get('title', '')}\n{job.get('description', '')}"
    return {
        "years_required": years_required(job.get("description", "")),
        "auth_flags": auth_flags(text),
        "employer_type": employer_type(job.get("company", ""), job.get("description", ""), job.get("job_type", "")),
        "fingerprint": fingerprint(job.get("company", ""), job.get("title", ""), job.get("location", "")),
    }
