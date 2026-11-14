"""Dice.com: public search page + job detail page (JobPosting JSON-LD). No login needed to search.

Selectors checked against dice.com on 2026-11-14:
  result card       [data-testid="job-card"]
  title link        a[data-testid="job-search-job-detail-link"]  (href /job-detail/<uuid>)
  company           [data-testid="job-card-company-name"]
  work-mode badge   [data-testid="locationTypeBadge"]  (detail page)
If Dice changes its markup, update the constants below; the fallbacks keep basic results working.
"""
from __future__ import annotations

import logging
from typing import Iterator
from urllib.parse import urlencode

from ..textutil import parse_relative, split_work_mode
from .base import BaseScraper, Card, JobDetail, RunContext
from .jsonld import posting_fields, read_job_posting

log = logging.getLogger("jobassist")

SEARCH_URL = "https://www.dice.com/jobs"
CARD = '[data-testid="job-card"]'
PAGE_SIZE = 20

POSTED = {"1h": "ONE", "24h": "ONE", "3d": "THREE", "7d": "SEVEN", "30d": None}
EMPLOYMENT = {"Full-time": "FULLTIME", "Part-time": "PARTTIME", "Contract": "CONTRACTS", "C2C": "THIRD_PARTY"}
WORKPLACE = {"Remote": "Remote", "Hybrid": "Hybrid", "On-site": "On-Site"}

_CARDS_JS = """els => els.map(c => {
  const a = c.querySelector('a[data-testid="job-search-job-detail-link"]') || c.querySelector('a[href*="/job-detail/"]');
  const co = c.querySelector('[data-testid="job-card-company-name"]');
  return {
    url: a ? a.href : '',
    title: a ? (a.innerText || a.getAttribute('aria-label') || '').trim() : '',
    company: co ? co.innerText.trim() : '',
    text: c.innerText || ''
  };
})"""

_DETAIL_FALLBACK_JS = """() => {
  const q = s => document.querySelector(s);
  const badge = q('[data-testid="locationTypeBadge"]');
  const header = q('[data-testid="job-detail-header-card"]');
  const main = q('main') || document.body;
  return {
    h1: (q('h1') || {}).innerText || '',
    badge: badge ? badge.innerText.trim() : '',
    header: header ? header.innerText : '',
    text: main.innerText.slice(0, 20000)
  };
}"""


def build_search_url(profile: dict, keyword: str, location: str, page_no: int) -> str:
    params: list[tuple[str, str]] = [("q", keyword)]
    if location and location.lower() != "remote":
        params.append(("location", location))
    params += [("page", str(page_no)), ("pageSize", str(PAGE_SIZE))]
    posted = POSTED.get(profile.get("posted_within") or "")
    if posted:
        params.append(("filters.postedDate", posted))
    emp = [EMPLOYMENT[t] for t in profile.get("job_types", []) if t in EMPLOYMENT]
    if emp:
        params.append(("filters.employmentType", "|".join(emp)))
    modes = list(profile.get("work_modes", []))
    if location.lower() == "remote" and "Remote" not in modes:
        modes = ["Remote"]
    work = [WORKPLACE[m] for m in modes if m in WORKPLACE]
    if work and len(work) < len(WORKPLACE):
        params.append(("filters.workplaceTypes", "|".join(work)))
    return f"{SEARCH_URL}?{urlencode(params)}"


def _card_meta(text: str) -> tuple[str, str]:
    """Card text has a line like 'Plano, Texas • Today'."""
    for line in text.splitlines():
        if "•" in line:
            loc, _, posted = line.partition("•")
            return loc.strip(), posted.strip()
    return "", ""


class DiceScraper(BaseScraper):
    key = "dice"
    name = "Dice"
    login_url = "https://www.dice.com/dashboard/login"

    def search(self, ctx: RunContext, page, profile: dict, keyword: str, location: str) -> Iterator[Card]:
        for page_no in range(1, int(ctx.s["max_pages_per_search"]) + 1):
            url = build_search_url(profile, keyword, location, page_no)
            log.info(f"Dice search p{page_no}: {url}")
            ctx.goto(page, url)
            try:
                page.wait_for_selector(CARD, timeout=15000)
            except Exception:
                log.info("  no results on this page")
                return
            ctx.human_scroll(page, 2)
            rows = page.eval_on_selector_all(CARD, _CARDS_JS)
            cards = []
            for r in rows:
                if "/job-detail/" not in r["url"]:
                    continue
                loc, posted = _card_meta(r["text"])
                mode, loc = split_work_mode(loc)
                ext = r["url"].rstrip("/").split("/job-detail/")[-1].split("?")[0]
                cards.append(Card(url=f"https://www.dice.com/job-detail/{ext}", title=r["title"], company=r["company"],
                                  location=loc, posted_text=posted, posted_at=parse_relative(posted),
                                  work_mode=mode, external_id=ext))
            log.info(f"  {len(cards)} cards")
            yield from cards
            if len(cards) < PAGE_SIZE // 2:
                return
            ctx.delay()

    def fetch_detail(self, ctx: RunContext, page, card: Card) -> JobDetail:
        ctx.goto(page, card.url)
        try:
            page.wait_for_selector('h1, script[type="application/ld+json"]', state="attached", timeout=15000)
        except Exception:
            pass
        posting = read_job_posting(page)
        fb = page.evaluate(_DETAIL_FALLBACK_JS)
        f = posting_fields(posting) if posting else {}
        badge = fb.get("badge", "")
        work_mode = {"remote": "Remote", "hybrid": "Hybrid", "on-site": "On-site", "onsite": "On-site"}.get(
            badge.lower(), f.get("work_mode", ""))
        description = f.get("description") or fb.get("text", "")
        return JobDetail(
            url=card.url,
            title=f.get("title") or fb.get("h1") or card.title,
            company=f.get("company") or card.company,
            location=f.get("location") or card.location,
            work_mode=work_mode,
            job_type=f.get("job_type", ""),
            posted_at=f.get("posted_at", ""),
            posted_text=card.posted_text,
            description=description,
            external_id=f.get("external_id") or card.external_id,
        )
