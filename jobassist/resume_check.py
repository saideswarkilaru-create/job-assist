"""Resume check: what a recruiter and an applicant tracking system (ATS) would flag. Offline.

Only suggestions: nothing here edits the resume. Each item: level good | tip | fix, a title and a detail.
Score: 100 minus weighted problems (fix = 10, tip = 4), floored at 0.
"""
from __future__ import annotations

import re

from . import skills
from .resume_doc import EMAIL, PHONE, ResumeDoc, all_text
from .resume_insights import estimate_experience

WEAK_OPENERS = re.compile(r"^(responsible for|worked on|helped|assisted( with| in)?|involved in|participated in|"
                          r"duties included|tasked with|handled)\b", re.I)
NUMBER = re.compile(r"\d")


def check(rd: ResumeDoc, custom_skills: str = "", source: str = ".docx") -> dict:
    """`source` = the uploaded file's extension (.docx / .pdf / .doc)."""
    text = all_text(rd)
    items: list[dict] = []

    def add(level, title, detail=""):
        items.append({"level": level, "title": title, "detail": detail})

    contact = " ".join([rd.name, *rd.contact, rd.header_footer_text])
    # --- contact
    add("good" if rd.name else "fix", "Your name is at the top" if rd.name else "Name not found at the top",
        "" if rd.name else "Put your full name on the first line, on its own.")
    add("good" if EMAIL.search(contact) else "fix", "Email address" if EMAIL.search(contact) else "No email address in the header",
        "" if EMAIL.search(contact) else "Recruiters need it to reach you; add it under your name.")
    add("good" if PHONE.search(contact) else "tip", "Phone number" if PHONE.search(contact) else "No phone number",
        "" if PHONE.search(contact) else "US recruiters often call first. Add a US number if you have one.")
    linkedin = re.search(r"linkedin\.com/in/", contact + " " + " ".join(l.url for l in rd.links), re.I)
    add("good" if linkedin else "tip", "LinkedIn profile link" if linkedin else "No LinkedIn link",
        "" if linkedin else "Add your LinkedIn URL (linkedin.com/in/your-name). Most recruiters check it.")
    if rd.header_footer_text and EMAIL.search(rd.header_footer_text):
        add("fix", "Contact details are in the page header/footer",
            "Some ATS skip headers and footers. Move them into the main page, or pick a design below.")

    # --- structure
    kinds = {s.kind for s in rd.sections}
    for kind, label in (("experience", "Experience"), ("skills", "Skills"), ("education", "Education")):
        if kind in kinds:
            add("good", f"{label} section found")
        elif kind == "experience" and "projects" in kinds:
            add("tip", "No Experience section", "You have Projects, which is fine for a new grad; add internships if you have any.")
        else:
            add("fix" if kind != "education" else "tip", f"No {label} section found",
                f"Add a clear '{label}' heading so ATS can find it.")

    # --- ATS-unfriendly layout
    if rd.text_boxes:
        add("fix", f"{rd.text_boxes} text box(es)", "Text inside text boxes is often invisible to ATS. Pick one of the designs below.")
    if rd.images:
        add("tip", "Images or icons in the resume", "ATS ignore images; make sure nothing important is only in a picture or icon.")
    if rd.tables:
        add("tip", f"{rd.tables} table(s)", "Most modern ATS read simple tables, but some older ones jumble them. The designs below use none.")
    if source == ".pdf":
        add("tip", "Converted from PDF", "The text is kept, but the layout may have shifted. Choosing a design gives you a clean Word file.")

    # --- length
    words = len(re.findall(r"\w+", text))
    years = estimate_experience(text)["years"] or 0
    if words > 1100 or (years < 5 and words > 750):
        add("tip", f"Long for your experience (~{words} words)",
            "With under 5 years, aim for one page (about 450–700 words). Cut older or less relevant bullets.")
    elif words < 200:
        add("tip", f"Very short (~{words} words)", "Add projects, internships or coursework that show your skills.")
    else:
        add("good", f"Good length (~{words} words)")

    # --- bullets
    bullets = [b for s in rd.sections for e in s.entries for b in e.bullets]
    if bullets:
        with_numbers = sum(1 for b in bullets if NUMBER.search(b))
        share = with_numbers / len(bullets)
        if share < 0.3:
            add("tip", f"Only {with_numbers} of {len(bullets)} bullets show a result with a number",
                "Where it's true, add scale or results (users, % faster, hours saved). Never invent numbers.")
        else:
            add("good", f"{with_numbers} of {len(bullets)} bullets show measurable results")
        weak = [b for b in bullets if WEAK_OPENERS.match(b)]
        if weak:
            add("tip", f"{len(weak)} bullet(s) start with a weak phrase",
                "Start with an action verb (Built, Led, Automated, Reduced…). For example: \"" + weak[0][:80] + "\"")
        long = [b for b in bullets if len(b) > 220]
        if long:
            add("tip", f"{len(long)} bullet(s) are very long", "Keep bullets to one or two lines so they get read.")
    elif "experience" in kinds or "projects" in kinds:
        add("tip", "No bullet points found under Experience/Projects",
            "Use bullet points for each job; recruiters skim them first.")

    # --- dates and skills
    if estimate_experience(text)["years"] is None and ("experience" in kinds):
        add("tip", "No dates found in Experience", "Add month and year for each job, e.g. Jun 2024 – Present.")
    found = skills.find(text, skills.library(custom_skills or ""))
    if len(found) < 8:
        add("tip", f"Only {len(found)} recognised technical skills",
            "List your tools and technologies in a Skills section using their common names (e.g. Spring Boot, AWS, SQL).")
    else:
        add("good", f"{len(found)} technical skills recognised")

    penalty = sum(10 if i["level"] == "fix" else 4 if i["level"] == "tip" else 0 for i in items)
    order = {"fix": 0, "tip": 1, "good": 2}
    items.sort(key=lambda i: order[i["level"]])
    return {"score": max(0, 100 - penalty), "items": items, "words": words}
