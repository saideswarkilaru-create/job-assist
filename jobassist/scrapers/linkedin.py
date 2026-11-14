"""LinkedIn Jobs: normal search page + job view page. Works logged out (public pages) and logged in.

Checked 2026-11-14 (public layout): cards carry data-entity-urn="urn:li:jobPosting:<id>",
.base-search-card__title / __subtitle, .job-search-card__location, <time datetime>.
Logged-in layout: list items carry data-occludable-job-id; details in #job-details.
IDs come from attributes and /jobs/view/<id> links, so class-name churn doesn't break discovery.
"""
from __future__ import annotations

import logging
import re
from typing import Iterator
from urllib.parse import urlencode

from ..textutil import parse_relative, split_work_mode
from .base import BaseScraper, Card, JobDetail, RunContext

log = logging.getLogger("jobassist")

SEARCH_URL = "https://www.linkedin.com/jobs/search/"
PAGE_SIZE = 25
POSTED_SECONDS = {"1h": 3600, "24h": 86400, "3d": 259200, "7d": 604800, "30d": 2592000}
WORKPLACE = {"On-site": "1", "Remote": "2", "Hybrid": "3"}
JOB_TYPE = {"Full-time": "F", "Contract": "C", "C2C": "C", "Part-time": "P"}
EXPERIENCE = {"Entry": ["2", "3"], "Mid": ["3", "4"], "Senior": ["4"]}

_CARDS_JS = r"""() => {
  const out = [], seen = new Set();
  const txt = e => e ? (e.innerText || '').trim() : '';
  const push = (id, root) => {
    if (!id || !/^\d+$/.test(id) || seen.has(id)) return;
    seen.add(id);
    const q = s => root ? root.querySelector(s) : null;
    const t = q('time');
    out.push({
      id,
      title: txt(q('.base-search-card__title') || q('.job-card-list__title--link') || q('.job-card-list__title') || q('a[href*="/jobs/view/"] strong') || q('a[href*="/jobs/view/"]')).split('\n')[0],
      company: txt(q('.base-search-card__subtitle') || q('.artdeco-entity-lockup__subtitle') || q('.job-card-container__primary-description')),
      location: txt(q('.job-search-card__location') || q('.artdeco-entity-lockup__caption') || q('.job-card-container__metadata-item')),
      datetime: t ? (t.getAttribute('datetime') || '') : '',
      posted: txt(t)
    });
  };
  document.querySelectorAll('[data-entity-urn*="jobPosting:"]').forEach(e => push((e.getAttribute('data-entity-urn').match(/jobPosting:(\d+)/) || [])[1], e));
  document.querySelectorAll('[data-occludable-job-id]').forEach(e => push(e.getAttribute('data-occludable-job-id'), e));
  document.querySelectorAll('[data-job-id]').forEach(e => push(e.getAttribute('data-job-id'), e));
  document.querySelectorAll('a[href*="/jobs/view/"]').forEach(a => {
    const m = a.href.match(/\/jobs\/view\/(?:[^/?]*-)?(\d+)/);
    if (m) push(m[1], a.closest('li') || a.parentElement);
  });
  return out;
}"""

_SCROLL_LIST_JS = r"""() => {
  const li = document.querySelector('[data-occludable-job-id]');
  let el = li ? li.parentElement : null;
  while (el && el !== document.body && el.scrollHeight <= el.clientHeight + 5) el = el.parentElement;
  if (el && el !== document.body) { el.scrollTop += 900; return true; }
  window.scrollBy(0, 900); return false;
}"""

_DETAIL_JS = r"""() => {
  const q = s => document.querySelector(s);
  const txt = e => e ? (e.innerText || '').trim() : '';
  const desc = q('#job-details') || q('.jobs-description__content') || q('.jobs-box__html-content') ||
               q('.show-more-less-html__markup') || q('.description__text');
  const buttons = [...document.querySelectorAll('button, a')].map(b => (b.innerText || '').trim());
  return {
    title: txt(q('.job-details-jobs-unified-top-card__job-title h1') || q('.top-card-layout__title') || q('h1')),
    company: txt(q('.job-details-jobs-unified-top-card__company-name') || q('.topcard__org-name-link') || q('.top-card-layout__second-subline a')),
    meta: [txt(q('.job-details-jobs-unified-top-card__tertiary-description-container') || q('.job-details-jobs-unified-top-card__primary-description-container') ||
              q('.top-card-layout__second-subline') || q('.topcard__flavor-row')),
           txt(q('.num-applicants__caption'))].join(' · '),
    prefs: [...document.querySelectorAll('.job-details-fit-level-preferences button, .job-details-preferences-and-skills, .description__job-criteria-item, .ui-label')]
             .map(e => (e.innerText || '').replace(/\s+/g, ' ').trim()).join(' | '),
    description: desc ? desc.innerText : '',
    easy: buttons.some(t => /easy apply/i.test(t)),
    apply: buttons.some(t => /^apply\b/i.test(t))
  };
}"""


def build_search_url(profile: dict, keyword: str, location: str, page_no: int) -> str:
    modes = list(profile.get("work_modes") or [])
    loc = location
    if location.strip().lower() == "remote":
        loc, modes = "United States", ["Remote"]
    params = [("keywords", keyword), ("location", loc or "United States")]
    secs = POSTED_SECONDS.get(profile.get("posted_within") or "")
    if secs:
        params.append(("f_TPR", f"r{secs}"))
    wt = [WORKPLACE[m] for m in modes if m in WORKPLACE]
    if wt and len(wt) < 3:
        params.append(("f_WT", ",".join(wt)))
    jt = sorted({JOB_TYPE[t] for t in profile.get("job_types", []) if t in JOB_TYPE})
    if jt:
        params.append(("f_JT", ",".join(jt)))
    ex = sorted({e for lvl in profile.get("experience_levels", []) for e in EXPERIENCE.get(lvl, [])})
    if ex and len(profile.get("experience_levels", [])) < 3:
        params.append(("f_E", ",".join(ex)))
    if page_no > 1:
        params.append(("start", str((page_no - 1) * PAGE_SIZE)))
    return f"{SEARCH_URL}?{urlencode(params)}"


def job_url(job_id: str) -> str:
    return f"https://www.linkedin.com/jobs/view/{job_id}/"


def parse_meta(meta: str, prefs: str) -> dict:
    """Pull work mode, job type, posted time and applicant count out of the top-card text."""
    blob = f"{meta} | {prefs}"
    out = {"work_mode": "", "job_type": "", "posted_text": "", "applicants": ""}
    m = re.search(r"\b(Remote|Hybrid|On-site)\b", blob, re.I)
    if m:
        out["work_mode"] = {"remote": "Remote", "hybrid": "Hybrid", "on-site": "On-site"}[m.group(1).lower()]
    m = re.search(r"\b(Full-time|Contract|Part-time|Temporary|Internship)\b", blob, re.I)
    if m:
        out["job_type"] = {"temporary": "Contract", "internship": "Part-time"}.get(m.group(1).lower(), m.group(1).capitalize())
    m = re.search(r"(Reposted\s+)?(\d+\s+\w+\s+ago|just now)", meta, re.I)
    if m:
        out["posted_text"] = m.group(0)
    m = re.search(r"((?:over\s+)?\d[\d,]*\+?\s+applicants?|be among the first \d+ applicants)", blob, re.I)
    if m:
        out["applicants"] = m.group(1)
    return out


class LinkedInScraper(BaseScraper):
    key = "linkedin"
    name = "LinkedIn"
    login_url = "https://www.linkedin.com/login"

    def search(self, ctx: RunContext, page, profile: dict, keyword: str, location: str) -> Iterator[Card]:
        for page_no in range(1, int(ctx.s["max_pages_per_search"]) + 1):
            url = build_search_url(profile, keyword, location, page_no)
            log.info(f"LinkedIn search p{page_no}: {url}")
            ctx.goto(page, url)
            try:
                page.wait_for_selector('[data-entity-urn*="jobPosting:"], [data-occludable-job-id], a[href*="/jobs/view/"]',
                                       state="attached", timeout=15000)
            except Exception:
                log.info("  no results")
                return
            for _ in range(4):  # let the (virtualized) list render more cards
                page.evaluate(_SCROLL_LIST_JS)
                ctx.sleep(0.8)
            rows = page.evaluate(_CARDS_JS)
            cards = []
            for r in rows:
                mode, loc = split_work_mode(r["location"])
                posted_at = parse_relative(r["posted"]) or (r["datetime"] + "T12:00:00+00:00" if r["datetime"] else "")
                cards.append(Card(url=job_url(r["id"]), title=r["title"], company=r["company"], location=loc,
                                  posted_text=r["posted"], posted_at=posted_at, work_mode=mode, external_id=r["id"]))
            log.info(f"  {len(cards)} cards")
            yield from cards
            if len(cards) < PAGE_SIZE // 2:
                return
            ctx.delay()

    def fetch_detail(self, ctx: RunContext, page, card: Card) -> JobDetail:
        ctx.goto(page, card.url)
        try:
            page.wait_for_selector("#job-details, .show-more-less-html__markup, .description__text, .jobs-description__content",
                                   state="attached", timeout=15000)
        except Exception:
            pass
        ctx.human_scroll(page, 1)
        d = page.evaluate(_DETAIL_JS)
        meta = parse_meta(d["meta"], d["prefs"])
        return JobDetail(
            url=card.url,
            title=d["title"] or card.title,
            company=d["company"] or card.company,
            location=card.location,
            work_mode=meta["work_mode"] or card.work_mode,
            job_type=meta["job_type"],
            posted_at=card.posted_at or parse_relative(meta["posted_text"]),
            posted_text=card.posted_text or meta["posted_text"],
            description=d["description"].strip(),
            external_id=card.external_id,
            applicants=meta["applicants"],
            apply_type="easy_apply" if d["easy"] else ("external" if d["apply"] else ""),
        )
