"""Indeed (US): normal search page + viewjob page.

Checked 2026-11-14: result links a[data-jk] (job key), [data-testid="company-name"],
[data-testid="text-location"] ("Hybrid work in Southlake, TX"); job page description in
.simple-job-description-html (new) or #jobDescriptionText (classic).
Indeed often shows a Cloudflare "verify you are human" page: the run pauses for you.
"""
from __future__ import annotations

import logging
import re
from typing import Iterator
from urllib.parse import urlencode

from ..textutil import parse_relative, split_work_mode
from .base import BaseScraper, Card, JobDetail, RunContext

log = logging.getLogger("jobassist")

SEARCH_URL = "https://www.indeed.com/jobs"
PAGE_SIZE = 10
FROMAGE = {"1h": "1", "24h": "1", "3d": "3", "7d": "7", "30d": "14"}
JOB_TYPE = {"Full-time": "fulltime", "Contract": "contract", "C2C": "contract", "Part-time": "parttime"}

_CARDS_JS = r"""() => [...document.querySelectorAll('a[data-jk]')].map(a => {
  const card = a.closest('.job_seen_beacon, li, td.resultContent, div.cardOutline') || a.parentElement;
  const q = s => card ? card.querySelector(s) : null;
  const txt = e => e ? (e.innerText || '').trim() : '';
  return {
    jk: a.getAttribute('data-jk'),
    title: (a.querySelector('span[title]') ? a.querySelector('span[title]').getAttribute('title') : txt(a)),
    company: txt(q('[data-testid="company-name"]') || q('.companyName')),
    location: txt(q('[data-testid="text-location"]') || q('.companyLocation')),
    posted: txt(q('[data-testid="myJobsStateDate"]') || q('span.date'))
  };
})"""

_DETAIL_JS = r"""() => {
  const pane = document.querySelector('#jobsearch-ViewjobPaneWrapper, .jobsearch-RightPane, [data-testid="viewJobBodyContainer"]') || document;
  const q = s => pane.querySelector(s) || document.querySelector(s);
  const txt = e => e ? (e.innerText || '').trim() : '';
  const desc = q('#jobDescriptionText') || q('.simple-job-description-html') || q('[data-testid="jobDescriptionText"]') ||
               q('[class*="jobDescription"]');
  const apply = txt(q('[data-testid="primary-apply-action"]') || q('#indeedApplyButton') || q('[data-testid="viewjob-apply"]') ||
                    q('#applyButtonLinkContainer'));
  return {
    title: txt(q('[data-testid="vj-job-title"]') || q('[data-testid="jobsearch-JobInfoHeader-title"]') || q('h1')),
    company: txt(q('[data-testid="inlineHeader-companyName"]') || q('[data-testid="company-info-metadata"] a') ||
                 q('[data-company-name]')),
    details: txt(q('#jobDetailsSection') || q('[aria-label="Job details"]') || q('[data-testid="company-info-metadata"]')),
    description: desc ? desc.innerText : '',
    apply
  };
}"""


def build_search_url(profile: dict, keyword: str, location: str, page_no: int) -> str:
    params = [("q", keyword), ("l", location or "United States")]
    age = FROMAGE.get(profile.get("posted_within") or "")
    if age:
        params.append(("fromage", age))
    types = {JOB_TYPE[t] for t in profile.get("job_types", []) if t in JOB_TYPE}
    if len(types) == 1:
        params.append(("jt", types.pop()))
    if page_no > 1:
        params.append(("start", str((page_no - 1) * PAGE_SIZE)))
    return f"{SEARCH_URL}?{urlencode(params)}"


def job_url(jk: str) -> str:
    return f"https://www.indeed.com/viewjob?jk={jk}"


class IndeedScraper(BaseScraper):
    key = "indeed"
    name = "Indeed"
    login_url = "https://secure.indeed.com/auth"

    def search(self, ctx: RunContext, page, profile: dict, keyword: str, location: str) -> Iterator[Card]:
        for page_no in range(1, int(ctx.s["max_pages_per_search"]) + 1):
            url = build_search_url(profile, keyword, location, page_no)
            log.info(f"Indeed search p{page_no}: {url}")
            ctx.goto(page, url)
            try:
                page.wait_for_selector("a[data-jk]", state="attached", timeout=15000)
            except Exception:
                log.info("  no results")
                return
            ctx.human_scroll(page, 2)
            rows = page.evaluate(_CARDS_JS)
            cards, seen = [], set()
            for r in rows:
                if not r["jk"] or r["jk"] in seen:
                    continue
                seen.add(r["jk"])
                mode, loc = split_work_mode(r["location"])
                cards.append(Card(url=job_url(r["jk"]), title=r["title"], company=r["company"], location=loc,
                                  posted_text=r["posted"], posted_at=parse_relative(r["posted"]),
                                  work_mode=mode, external_id=r["jk"], source_url=url))
            log.info(f"  {len(cards)} cards")
            yield from cards
            if len(cards) < PAGE_SIZE // 2:
                return
            ctx.delay()

    def fetch_detail(self, ctx: RunContext, page, card: Card) -> JobDetail:
        """Read the job in the results page's side panel (click the card, like a person would).
        Indeed often sends stand-alone job pages to a sign-in wall; the panel does not need one."""
        jk = card.external_id
        link = page.query_selector(f'a[data-jk="{jk}"]')
        if link is None and card.source_url:
            ctx.goto(page, f"{card.source_url}&vjk={jk}")
        elif link is None:
            ctx.goto(page, card.url)
        else:
            link.scroll_into_view_if_needed()
            ctx.sleep(0.5)
            link.click()
        try:
            page.wait_for_function(f"location.href.includes('{jk}')", timeout=10000)
            page.wait_for_selector("#jobDescriptionText, .simple-job-description-html, [data-testid='jobDescriptionText']",
                                   state="attached", timeout=15000)
            ctx.sleep(1.2)  # let the panel finish swapping content
        except Exception:
            pass
        d = page.evaluate(_DETAIL_JS)
        m = re.search(r"\b(Full-time|Contract|Part-time|Temporary|Internship)\b", d["details"] + " " + d["description"][:600], re.I)
        job_type = {"temporary": "Contract", "internship": "Part-time"}.get(m.group(1).lower(), m.group(1).capitalize()) if m else ""
        apply = d["apply"].lower()
        return JobDetail(
            url=card.url,
            title=d["title"].replace("- job post", "").strip() or card.title,
            company=card.company or d["company"],
            location=card.location,
            work_mode=card.work_mode,
            job_type=job_type,
            posted_at=card.posted_at,
            posted_text=card.posted_text,
            description=d["description"].strip(),
            external_id=card.external_id,
            apply_type="external" if "company site" in apply else ("easy_apply" if "apply" in apply else ""),
        )
