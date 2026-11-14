"""Apply-assist: open the application, fill it honestly, and STOP before the final Submit.

Never auto-submits: the final button is only clicked by submit_application(), which runs only when the
person presses "Approve & Submit" for that one application. The person can also click the site's own
Submit; confirmation pages are detected and the application is logged.

Honesty rules:
- Answers come only from My details (config/profile.yaml), Settings and the person's own Q&A list.
- Per-skill experience questions ("years with Kafka"), essays, salary (unless set) -> "needs you".
- Sensitive identifiers (SSN, date of birth, bank, passport...) -> never filled, always "needs you".
- Terms / consent / certification checkboxes are never ticked by the app.
- Fields the site already filled (e.g. LinkedIn profile data) are left as they are.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from . import applicant as applicant_mod
from . import skills

log = logging.getLogger("jobassist")

# ------------------------------------------------------------------ page scripts
_FIELDS_JS = r"""(startId) => {
  let n = startId;
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
                     return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none'
                            && s.opacity !== '0' && e.getAttribute('aria-hidden') !== 'true'; };
  const txt = e => (e ? (e.innerText || e.textContent || '') : '').replace(/\s+/g, ' ').trim();
  const strip = node => { const c = node.cloneNode(true); c.querySelectorAll('input,select,textarea,option,button,script,style').forEach(x => x.remove()); return txt(c); };
  const labelOf = el => {
    let t = '';
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) t = txt(l); }
    if (!t) { const l = el.closest('label'); if (l) t = strip(l); }
    if (!t && el.getAttribute('aria-labelledby'))
      t = el.getAttribute('aria-labelledby').split(/\s+/).map(id => txt(document.getElementById(id))).join(' ');
    if (!t) t = el.getAttribute('aria-label') || '';
    if (!t) { const fs = el.closest('fieldset'); const lg = fs && fs.querySelector('legend'); if (lg) t = txt(lg); }
    if (!t) { const box = el.closest('[class*="field" i], [class*="question" i], [class*="form-group" i], li');
              if (box) t = strip(box).slice(0, 220); }
    return (t || el.getAttribute('placeholder') || el.name || '').slice(0, 300);
  };
  const groupLabel = el => {
    const fs = el.closest('fieldset'); if (fs) { const lg = fs.querySelector('legend'); if (lg) return txt(lg); }
    const grp = el.closest('[role="radiogroup"], [role="group"]');
    if (grp) { const lb = grp.getAttribute('aria-labelledby'); if (lb) return txt(document.getElementById(lb));
               if (grp.getAttribute('aria-label')) return grp.getAttribute('aria-label'); }
    const box = el.closest('[class*="field" i], [class*="question" i], [class*="form-group" i], li');
    if (box) { const c = box.cloneNode(true); c.querySelectorAll('input,label,select,textarea,button').forEach(x => x.remove());
               const t = txt(c); if (t) return t.slice(0, 220); }
    return '';
  };
  const out = [], groups = {};
  for (const el of document.querySelectorAll('input, select, textarea')) {
    const type = (el.getAttribute('type') || el.tagName).toLowerCase();
    if (['hidden', 'submit', 'button', 'image', 'reset', 'search', 'password'].includes(type)) continue;
    if (type !== 'file' && !vis(el)) continue;
    if (el.disabled || el.readOnly) continue;
    const label = labelOf(el);
    const required = el.required || el.getAttribute('aria-required') === 'true' || /\*\s*$/.test(label);
    const multiCheck = type === 'checkbox' && el.name && document.querySelectorAll(`input[type=checkbox][name="${CSS.escape(el.name)}"]`).length > 1;
    if (type === 'radio' || multiCheck) {
      const key = type + ':' + (el.name || groupLabel(el));
      if (!groups[key]) {
        groups[key] = { id: n++, kind: type === 'radio' ? 'radio' : 'checkgroup', label: groupLabel(el) || label,
                        name: el.name || '', options: [], required, value: '' };
        out.push(groups[key]);
      }
      const g = groups[key];
      el.setAttribute('data-ja', g.id + '-' + g.options.length);
      g.options.push(label || el.value);
      g.required = g.required || required;
      if (el.checked) g.value = label || el.value;
      continue;
    }
    el.setAttribute('data-ja', String(n));
    const combo = el.getAttribute('role') === 'combobox' || el.getAttribute('aria-autocomplete') === 'list';
    // A dropdown counts as answered only if someone picked an option (or the site explicitly pre-selected one),
    // never when it just shows a placeholder like "Select..." or its first option by default.
    let selectValue = '';
    if (el.tagName === 'SELECT') {
      const o = el.options[el.selectedIndex];
      const placeholder = !o || o.disabled || o.value === '' || /^\s*(select|choose|please|--|none\b)/i.test(o.text);
      selectValue = (!placeholder && (el.selectedIndex > 0 || o.defaultSelected)) ? o.text.trim() : '';
    }
    out.push({ id: n++, kind: el.tagName === 'SELECT' ? 'select' : el.tagName === 'TEXTAREA' ? 'textarea'
                         : type === 'checkbox' ? 'checkbox' : type === 'file' ? 'file' : combo ? 'combobox' : 'text',
               type, label, name: el.name || '', hint: ((el.id || '') + ' ' + (el.name || '')).toLowerCase(), required,
               value: el.tagName === 'SELECT' ? selectValue : type === 'checkbox' ? (el.checked ? 'checked' : '')
                      : type === 'file' ? (el.files && el.files.length ? el.files[0].name : '') : (el.value || ''),
               options: el.tagName === 'SELECT' ? [...el.options].map(o => o.text.trim()).filter(Boolean) : [],
               accept: el.getAttribute('accept') || '' });
  }
  return { fields: out, next: n };
}"""

_BUTTONS_JS = r"""() => {
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
                     return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  return [...document.querySelectorAll('button, input[type=submit], input[type=button], a[role=button], [role=button], a')]
    .filter(vis).map((b, i) => { b.setAttribute('data-jab', String(i));
      return { i, text: (b.innerText || b.value || b.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim().slice(0, 80),
               disabled: !!b.disabled || b.getAttribute('aria-disabled') === 'true', tag: b.tagName,
               submit: (b.type || '').toLowerCase() === 'submit', inForm: !!b.closest('form') }; });
}"""

_HIGHLIGHT_JS = r"""(i) => { const b = document.querySelector(`[data-jab="${i}"]`); if (!b) return false;
  b.style.outline = '4px solid #d93025'; b.style.outlineOffset = '3px'; b.scrollIntoView({ block: 'center' }); return true; }"""

_TEXT_JS = "() => (document.body ? document.body.innerText : '').slice(0, 20000)"

# ------------------------------------------------------------------ button classes
FINAL_RX = re.compile(r"^(submit|submit (my |your |the )?application|send( my)? application|apply|apply now|finish|"
                      r"complete( my)? application|confirm|confirm (and|&) submit|submit & apply)$", re.I)
NEXT_RX = re.compile(r"^(next|next step|continue|continue to next step|review|review (my |your )?application|"
                     r"save (and|&) continue|proceed|next page)$", re.I)
START_RX = re.compile(r"^(easy apply|apply|apply now|apply for this (job|position|role)|apply to this job|"
                      r"apply on company site|i'?m interested|start (my |your )?application|apply here)$", re.I)
CONFIRM_RX = re.compile(r"application (has been |was )?(successfully )?(submitted|received|sent)|thank(s| you) for (applying|your application)|"
                        r"we(?:'ve| have) received your application|your application is complete|successfully applied|"
                        r"application complete|you(?:'ve| have) applied", re.I)
ERROR_RX = re.compile(r"(this field is required|please (enter|select|complete|fill)|is required|invalid|error)", re.I)

# ------------------------------------------------------------------ question -> answer
SENSITIVE = re.compile(r"social security|\bssn\b|date of birth|\bdob\b|birth ?date|driver'?s licen[sc]e|passport (number|no)|"
                       r"bank|routing|account number|credit card|mother'?s maiden|tax id|\bitin\b|\bein\b", re.I)
CONSENT = re.compile(r"\b(agree|consent|terms|privacy (policy|notice)|certify|acknowledge|attest|authori[sz]e .*(background|check)|"
                     r"i understand|accurate (and|&) complete)\b", re.I)

RULES: list[tuple[re.Pattern, str]] = [(re.compile(rx, re.I), key) for rx, key in [
    # question types first: their keywords must win over contact words inside the same sentence
    (r"sponsor", "requires_sponsorship"),
    (r"(legally )?authori[sz]ed to work|eligible to work|right to work|work authori[sz]ation", "authorized_to_work"),
    (r"relocat", "willing_to_relocate"),
    (r"salary|compensation|pay expectation|desired pay|rate expectation", "expected_salary"),
    (r"notice period|start date|when can you start|available to start|availability", "notice_period"),
    (r"how did you (hear|find|learn)|source of (application|referral)|where did you (hear|see)", "how_heard"),
    (r"years of (professional |relevant |total )?(work )?experience|how many years|experience \(years\)", "years_total"),
    (r"gender|\bsex\b", "gender"),
    (r"\brace\b|ethnic|hispanic|latino", "race"),
    (r"veteran", "veteran"),
    (r"disab", "disability"),
    (r"cover ?letter", "cover_letter"),
    (r"resume|\bcv\b|curriculum vitae", "resume"),
    # contact / profile fields
    (r"first\s*name|given name|legal first", "first_name"),
    (r"last\s*name|surname|family name|legal last", "last_name"),
    (r"preferred (first )?name|nickname", "preferred_name"),
    (r"^(full |your |legal )?name\s*\*?$|full name|your name", "full_name"),
    (r"e-?mail", "email"),
    (r"phone|mobile|cell", "phone"),
    (r"linked\s*in", "linkedin_url"),
    (r"git\s*hub", "github_url"),
    (r"portfolio|personal (web)?site|website|\burl\b", "portfolio_url"),
    (r"street|address line|^address", "address"),
    (r"\bcity\b|town", "city"),
    (r"\bstate\b|province|region", "state"),
    (r"zip|postal", "zip"),
    (r"country", "country"),
    (r"^(current )?location\b|where are you (currently )?(located|based)", "location"),
    (r"current (job )?title|most recent (job )?title|job title", "current_title"),
    (r"current (company|employer)|most recent (company|employer)|employer name", "current_company"),
    (r"school|university|college|institution", "school"),
    (r"degree|education level|highest level of education", "degree"),
    (r"major|field of study|discipline|area of study", "major"),
    (r"graduation|grad date|year of completion", "graduation_date"),
    (r"\bgpa\b|grade point", "gpa"),
]]

US_STATES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
             "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
             "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
             "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
             "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
             "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
             "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
             "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
             "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
             "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia"}
_DECLINE_OPT = re.compile(r"decline|prefer not|don'?t wish|do not wish|not to (say|answer|disclose|self.?identify)|choose not", re.I)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


QUESTION_KEYS = {"requires_sponsorship", "authorized_to_work", "willing_to_relocate", "expected_salary", "notice_period",
                 "how_heard", "years_total", "gender", "race", "veteran", "disability", "location", "country",
                 "cover_letter", "resume"}
_QUESTION = re.compile(r"\?|^(are|do|did|have|has|will|would|is|can|could|what|which|how|please|were|if)\b", re.I)


def classify(label: str) -> str | None:
    lab = (label or "").strip()
    is_question = len(lab) > 40 and bool(_QUESTION.search(lab))
    for rx, key in RULES:
        if rx.search(lab):
            if is_question and key not in QUESTION_KEYS:
                continue   # "Are you bound by agreements with your current employer?" is not "current company"
            return key
    return None


def answer_for(label: str, a: dict, settings: dict, lib) -> tuple[str | None, str]:
    """(answer, source) for a question label, or (None, reason) when the person must answer."""
    lab = (label or "").strip()
    if not lab:
        return None, "unlabelled field"
    if SENSITIVE.search(lab):
        return None, "sensitive: please enter this yourself"
    for qa in a.get("answers") or []:  # the person's own answers win
        words = [w for w in _norm(qa["question"]).split() if len(w) > 2]
        if words and all(w in _norm(lab) for w in words):
            return qa["answer"], "your Q&A"
    key = classify(lab)
    if key is None:
        return None, "question the app can't answer for you"
    if key == "years_total":
        mentioned = [s for s in skills.find(lab, lib)]
        if mentioned:
            return None, f"asks years with {', '.join(mentioned)}; answer honestly yourself"
        yrs = settings.get("years_of_experience")
        return (str(int(yrs)) if yrs is not None and float(yrs).is_integer() else str(yrs)), "Settings"
    if key in ("resume", "cover_letter"):
        return key, "file"
    if key == "full_name":
        v = applicant_mod.full_name(a)
        return (v or None), ("My details" if v else "add your name in My details")
    if key == "location":
        v = ", ".join(x for x in (a.get("city"), a.get("state")) if x)
        return (v or None), ("My details" if v else "add city/state in My details")
    if key == "how_heard":
        site = settings.get("_site_label") or "Job board"
        return site, "job source"
    v = (a.get(key) or "").strip()
    if not v:
        return None, f"add '{key.replace('_', ' ')}' in My details" if key != "expected_salary" else "salary: answer yourself"
    return v, "My details"


def choose_option(options: list[str], answer: str) -> str | None:
    """Pick the option that means `answer` (exact, yes/no, state names, decline...)."""
    if not options or answer is None:
        return None
    ans = _norm(answer)
    opts = [(o, _norm(o)) for o in options]
    real = [(o, n) for o, n in opts if n and not re.match(r"^(select|choose|please select|none selected|\-+)( one| an option)?$", n)]
    for o, n in real:
        if n == ans:
            return o
    if ans in ("yes", "no"):
        for o, n in real:
            if re.match(rf"^{ans}\b", n):
                return o
        return None
    if _DECLINE_OPT.search(answer):
        return next((o for o, n in real if _DECLINE_OPT.search(o)), None)
    up = answer.strip().upper()
    alt = {_norm(US_STATES[up])} if up in US_STATES else {_norm(k) for k, v in US_STATES.items() if _norm(v) == ans}
    if ans in ("united states", "usa", "us", "united states of america"):
        alt |= {"united states", "usa", "us", "united states of america"}
    for o, n in real:
        if n in alt:
            return o
    for o, n in real:
        if ans and (n.startswith(ans) or ans.startswith(n)) and len(n) > 2:
            return o
    for o, n in real:
        if ans and ans in n:
            return o
    return None


# ------------------------------------------------------------------ fill
def _frames(page):
    return [page.main_frame] + [f for f in page.frames if f != page.main_frame]


def scan(page) -> list[tuple[object, dict]]:
    out, nid = [], 0
    for fr in _frames(page):
        try:
            res = fr.evaluate(_FIELDS_JS, nid)
        except Exception:
            continue
        nid = res["next"]
        out += [(fr, f) for f in res["fields"]]
    return out


def _pick_file(kind: str, files: dict, accept: str) -> str | None:
    want = files.get(kind) or []
    acc = accept.lower()
    for f in want:
        if not acc or Path(f).suffix.lower() in acc or "*" in acc:
            return f
    return want[0] if want else None


def fill(ctx, page, a: dict, settings: dict, files: dict, *, dry_run: bool = False) -> dict:
    """Fill every visible field we can answer honestly. Returns {'filled': [...], 'needs_you': [...]}."""
    lib = skills.library(settings.get("custom_skills", "") or "")
    filled, needs, kept = [], [], []
    for fr, f in scan(page):
        label, kind = re.sub(r"\s*(Select\.\.\.|Choose\.\.\.)\s*$", "", f["label"]), f["kind"]
        loc = fr.locator(f'[data-ja="{f["id"]}"]') if kind not in ("radio", "checkgroup") else None
        if kind in ("checkbox", "checkgroup"):
            if f["required"] and not f["value"]:
                why = "consent / terms: tick it yourself after reading" if CONSENT.search(label) else "tick what applies"
                needs.append({"label": label, "why": why})
            continue
        if kind == "file":
            want = "cover_letter" if re.search(r"cover", f"{label} {f.get('hint', '')}", re.I) else "resume"
            if f["value"]:
                kept.append({"label": label, "value": f["value"]})
                continue
            path = _pick_file(want, files, f["accept"])
            if not path:
                if f["required"] or want == "resume":
                    needs.append({"label": label or want, "why": f"no {want.replace('_', ' ')} file to attach"})
                continue
            if not dry_run:
                loc.set_input_files(path)
            filled.append({"label": label or "Resume", "value": Path(path).name, "source": "file"})
            continue
        if f["value"]:  # the site (or the person) already answered: leave it
            kept.append({"label": label, "value": f["value"]})
            continue
        ans, source = answer_for(label, a, settings, lib)
        if ans in ("resume", "cover_letter") and source == "file":
            if ans == "cover_letter" and kind == "textarea" and files.get("cover_text"):
                ans, source = files["cover_text"], "cover note"
            else:
                continue
        if ans is None:
            if f["required"] or source.startswith(("sensitive", "asks years", "salary")):
                needs.append({"label": label, "why": source})
            continue
        try:
            if kind in ("select", "radio"):
                opt = choose_option(f["options"], ans)
                if opt is None:
                    if f["required"]:
                        needs.append({"label": label, "why": f"no option matches '{ans}'"})
                    continue
                if not dry_run:
                    if kind == "select":
                        loc.select_option(label=opt)
                    else:
                        idx = f["options"].index(opt)
                        fr.locator(f'[data-ja="{f["id"]}-{idx}"]').check(force=True)
                filled.append({"label": label, "value": opt, "source": source})
            elif kind == "combobox":
                if not dry_run:
                    loc.fill(ans)
                    ctx.sleep(0.8)
                    loc.press("Enter")
                filled.append({"label": label, "value": ans, "source": source})
            else:
                if not dry_run:
                    loc.fill(ans)
                filled.append({"label": label, "value": ans if len(ans) < 120 else ans[:117] + "…", "source": source})
            if not dry_run:
                ctx.sleep(0.3)
        except Exception as e:
            needs.append({"label": label, "why": f"couldn't fill automatically ({type(e).__name__})"})
    return {"filled": filled, "needs_you": needs, "kept": kept}


# ------------------------------------------------------------------ buttons and steps
def find_button(page, rx: re.Pattern) -> tuple[object, dict] | None:
    """Best visible enabled button matching rx. Prefers a real submit inside a form and clear wording
    ("Submit application" over a page-top "Apply" that only scrolls down to the form)."""
    best, best_rank = None, 99
    for fr in _frames(page):
        try:
            buttons = fr.evaluate(_BUTTONS_JS)
        except Exception:
            continue
        for b in buttons:
            if not b["text"] or b["disabled"] or not rx.match(b["text"]):
                continue
            rank = (0 if b["submit"] and b["inForm"] else 2 if b["inForm"] else 4)
            rank += 0 if re.search(r"submit|send", b["text"], re.I) else 1
            if rank < best_rank:
                best, best_rank = (fr, b), rank
    return best


def has_form(page) -> bool:
    fields = [f for _, f in scan(page) if f["kind"] in ("text", "select", "textarea", "file", "combobox")]
    return len(fields) >= 2


def page_text(page) -> str:
    out = []
    for fr in _frames(page):
        try:
            out.append(fr.evaluate(_TEXT_JS))
        except Exception:
            pass
    return "\n".join(out)


def confirmed(page) -> bool:
    return bool(CONFIRM_RX.search(page_text(page)) or re.search(r"/(thank|thanks|confirmation|submitted|success)", page.url, re.I))


def open_application(ctx, page, url: str):
    """Go to the job and press its Apply button. Returns the page that holds the form (maybe a new tab)."""
    ctx.goto(page, url)
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    if has_form(page):
        return page
    hit = find_button(page, START_RX)
    if not hit:
        return page
    fr, b = hit
    log.info(f"  pressing '{b['text']}'")
    try:
        with page.context.expect_page(timeout=6000) as newp:
            fr.locator(f'[data-jab="{b["i"]}"]').click()
        target = newp.value
        log.info(f"  application opened in a new tab: {target.url[:100]}")
    except Exception:
        target = page
    try:
        target.wait_for_load_state("domcontentloaded", timeout=20000)
        target.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    ctx.sleep(1.5)
    from .scrapers.base import detect_block
    kind = detect_block(target)
    if kind:
        ctx.wait_for_user(target, kind)
    return target


def prepare(ctx, page, url: str, a: dict, settings: dict, files: dict, *, max_steps: int = 8) -> tuple[object, dict]:
    """Open + fill all steps up to (not including) the final Submit. Returns (form_page, report)."""
    form = open_application(ctx, page, url)
    report = {"filled": [], "needs_you": [], "kept": [], "steps": 0, "final_button": None, "url": "", "note": ""}
    for step in range(max_steps):
        r = fill(ctx, form, a, settings, files)
        for k in ("filled", "needs_you", "kept"):
            report[k] += r[k]
        report["steps"] = step + 1
        ctx.sleep(1)
        in_form = has_form(form)
        final = find_button(form, FINAL_RX) if in_form else None   # "Apply" on a plain job page is not a submit
        nxt = find_button(form, NEXT_RX)
        if final or not nxt:
            break
        required_open = [n for n in r["needs_you"] if not n["why"].startswith(("sensitive",))]
        if required_open:
            report["note"] = "Stopped on this step: some required questions need you before going on."
            break
        fr, b = nxt
        log.info(f"  step {step + 1}: pressing '{b['text']}'")
        fr.locator(f'[data-jab="{b["i"]}"]').click()
        ctx.sleep(2.5)
        try:
            form.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
    final = find_button(form, FINAL_RX) if has_form(form) else None
    if final:
        fr, b = final
        fr.evaluate(_HIGHLIGHT_JS, b["i"])
        report["final_button"] = b["text"]
    elif not report["note"]:
        report["note"] = ("No form found. The site may need you to sign in, or the job may be closed. "
                          "Use the browser window, then press 'Fill this page again'.") if not report["filled"] else \
            "Couldn't find the final Submit button; check the browser window."
    report["url"] = form.url
    try:
        form.bring_to_front()
    except Exception:
        pass
    return form, report


def submit_application(ctx, form) -> tuple[bool, str]:
    """Click the final Submit. Only called when the person pressed 'Approve & Submit' for this application."""
    if confirmed(form):
        return True, "already submitted"
    hit = find_button(form, FINAL_RX) if has_form(form) else None
    if not hit:
        return False, "Couldn't find the Submit button any more; please submit in the browser window."
    fr, b = hit
    fr.evaluate(_HIGHLIGHT_JS, b["i"])
    log.info(f"  you approved: pressing '{b['text']}'")
    fr.locator(f'[data-jab="{b["i"]}"]').click()
    for _ in range(10):
        ctx.sleep(1.5)
        if confirmed(form):
            return True, "submitted"
    if find_button(form, NEXT_RX) or find_button(form, FINAL_RX):
        return False, "The site didn't accept it yet (a required field or a check may be missing). Look at the browser window."
    return False, "Couldn't confirm. If you see a confirmation in the browser, press 'I submitted it'."
