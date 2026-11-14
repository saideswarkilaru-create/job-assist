"""Naukri (India): normal search page + job page. Off by default for US job seekers.

Checked 2026-11-14: cards .srp-jobtuple-wrapper[data-job-id], a.title, a.comp-name.
"""
from __future__ import annotations

import logging
import re
from typing import Iterator
from urllib.parse import urlencode

from ..textutil import parse_relative, split_work_mode
from .base import BaseScraper, Card, JobDetail, RunContext
from .jsonld import posting_fields, read_job_posting

log = logging.getLogger("jobassist")

JOB_AGE = {"1h": "1", "24h": "1", "3d": "3", "7d": "7", "30d": "30"}

_CARDS_JS = r"""() => [...document.querySelectorAll('.srp-jobtuple-wrapper, article.jobTuple')].map(c => {
  const q = s => c.querySelector(s);
  const txt = e => e ? (e.innerText || '').trim() : '';
  const a = q('a.title');
  return {
    id: c.getAttribute('data-job-id') || '',
    url: a ? a.href : '',
    title: txt(a),
    company: txt(q('a.comp-name') || q('.comp-name')),
    location: txt(q('.locWdth') || q('.loc-wrap') || q('.location')),
    experience: txt(q('.expwdth') || q('.exp-wrap')),
    posted: txt(q('.job-post-day') || q('.job-post-date'))
  };
})"""

_DETAIL_JS = r"""() => {
  const q = s => document.querySelector(s);
  const desc = q('[class*="dang-inner-html"]') || q('section[class*="job-desc"]') || q('.job-desc') || q('main');
  return { h1: (q('h1') || {}).innerText || '', description: desc ? desc.innerText : '' };
}"""


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def build_search_url(profile: dict, keyword: str, location: str, page_no: int) -> str:
    base = f"https://www.naukri.com/{_slug(keyword)}-jobs" + (f"-in-{_slug(location.split(',')[0])}" if location else "")
    if page_no > 1:
        base += f"-{page_no}"
    params = [("k", keyword)]
    if location:
        params.append(("l", location.split(",")[0].strip()))
    age = JOB_AGE.get(profile.get("posted_within") or "")
    if age:
        params.append(("jobAge", age))
    return f"{base}?{urlencode(params)}"


class NaukriScraper(BaseScraper):
    key = "naukri"
    name = "Naukri"
    login_url = "https://www.naukri.com/nlogin/login"

    def search(self, ctx: RunContext, page, profile: dict, keyword: str, location: str) -> Iterator[Card]:
        for page_no in range(1, int(ctx.s["max_pages_per_search"]) + 1):
            url = build_search_url(profile, keyword, location, page_no)
            log.info(f"Naukri search p{page_no}: {url}")
            ctx.goto(page, url)
            try:
                page.wait_for_selector(".srp-jobtuple-wrapper, article.jobTuple", timeout=15000)
            except Exception:
                log.info("  no results")
                return
            ctx.human_scroll(page, 2)
            rows = [r for r in page.evaluate(_CARDS_JS) if r["url"]]
            cards = []
            for r in rows:
                mode, loc = split_work_mode(r["location"])
                cards.append(Card(url=r["url"].split("?")[0], title=r["title"], company=r["company"], location=loc,
                                  posted_text=r["posted"], posted_at=parse_relative(r["posted"]),
                                  work_mode=mode, external_id=r["id"]))
            log.info(f"  {len(cards)} cards")
            yield from cards
            if len(cards) < 10:
                return
            ctx.delay()

    def fetch_detail(self, ctx: RunContext, page, card: Card) -> JobDetail:
        ctx.goto(page, card.url)
        try:
            page.wait_for_selector('h1, script[type="application/ld+json"]', state="attached", timeout=15000)
        except Exception:
            pass
        posting = read_job_posting(page)
        f = posting_fields(posting) if posting else {}
        fb = page.evaluate(_DETAIL_JS)
        return JobDetail(
            url=card.url, title=f.get("title") or fb["h1"] or card.title, company=f.get("company") or card.company,
            location=card.location or f.get("location", ""), work_mode=card.work_mode or f.get("work_mode", ""),
            job_type=f.get("job_type", ""), posted_at=f.get("posted_at") or card.posted_at,
            posted_text=card.posted_text, description=f.get("description") or fb["description"].strip(),
            external_id=card.external_id,
        )
