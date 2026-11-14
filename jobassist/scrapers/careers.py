"""Company career pages and custom job sites.

Order of attempts for a company:
1. Known applicant-tracking systems (ATS), searched by URL: Workday, Greenhouse, Lever, iCIMS,
   SmartRecruiters, Ashby, Oracle Cloud HCM.
2. Generic: open the careers page, follow a "search open roles / view jobs" link if there is one,
   find a job search box, type the keyword, press Enter, collect job links.
3. A custom adapter in adapters/<name>.py (set on Companies & Sites) replaces all of this.

Job pages are read with schema.org JobPosting JSON-LD first, then common description containers.
"""
from __future__ import annotations

import logging
import re
from typing import Iterator
from urllib.parse import quote_plus, urlsplit

from ..textutil import contains_term, parse_relative, split_work_mode
from .base import BaseScraper, Card, JobDetail, RunContext
from .jsonld import posting_fields, read_job_posting

log = logging.getLogger("jobassist")

# ------------------------------------------------------------------ ATS detection
ATS = [
    ("workday", re.compile(r"\.myworkdayjobs\.com|\.myworkdaysite\.com", re.I)),
    ("greenhouse", re.compile(r"(boards|job-boards)\.greenhouse\.io", re.I)),
    ("lever", re.compile(r"jobs\.lever\.co", re.I)),
    ("icims", re.compile(r"\.icims\.com", re.I)),
    ("smartrecruiters", re.compile(r"(careers|jobs)\.smartrecruiters\.com", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com", re.I)),
    ("oracle", re.compile(r"\.oraclecloud\.com/hcmUI/CandidateExperience", re.I)),
]


def detect_ats(url: str) -> str | None:
    for name, rx in ATS:
        if rx.search(url or ""):
            return name
    return None


def ats_search_url(ats: str, base: str, keyword: str) -> str | None:
    """URL that shows the ATS's own search results for `keyword` (None = list page, filter by title)."""
    p = urlsplit(base)
    root = f"{p.scheme}://{p.netloc}"
    kw = quote_plus(keyword)
    if ats == "workday":
        path = re.sub(r"/(job|details)/.*$", "", p.path).rstrip("/")
        return f"{root}{path}?q={kw}"
    if ats == "icims":
        return f"{root}/jobs/search?ss=1&searchKeyword={kw}&in_iframe=1"
    if ats == "smartrecruiters":
        company = p.path.strip("/").split("/")[0]
        return f"https://careers.smartrecruiters.com/{company}?search={kw}"
    if ats == "oracle":
        path = re.sub(r"/job/.*$", "", p.path).rstrip("/")
        return f"{root}{path}/jobs?keyword={kw}"
    return None  # greenhouse / lever / ashby list everything on one page


# ------------------------------------------------------------------ link discovery
_PORTAL_LINK = re.compile(
    r"search (?:open |all )?(?:roles|jobs|positions|openings)|view (?:all )?(?:jobs|openings|positions|roles)|"
    r"explore (?:jobs|opportunities|careers|roles)|(?:current|job|open) openings|find (?:a )?jobs|see (?:all )?open|"
    r"browse jobs|job search|open positions|career opportunities|apply now for careers", re.I)
_JOBLIKE = re.compile(r"/(?:jobs?|careers?|positions?|openings?|requisitions?|vacanc\w*|job-detail|jobdetail|"
                      r"postings?|opportunit\w*|req)/", re.I)
_NOT_JOB = re.compile(r"/(?:login|signin|register|saved|search|alerts?|faq|benefits|culture|students?|"
                      r"locations?|teams?|events?|blog|privacy|cookie)(?:[/?#]|$)", re.I)
_ID_LIKE = re.compile(r"\d{4,}|[0-9a-f]{8}-[0-9a-f]{4}|_[A-Z]?R?\d{3,}|/[a-z0-9]+(?:-[a-z0-9]+){2,}/?$", re.I)

_LINKS_JS = r"""() => [...document.querySelectorAll('a[href]')].map(a => {
  const row = a.closest('li, tr, article, [role="listitem"], [data-automation-id="listItem"], .opening, .posting') || a.parentElement;
  const loc = row ? (row.querySelector('[data-automation-id="locations"], .location, .job-location, [class*="location" i]') || {}).innerText : '';
  const posted = row ? (row.querySelector('[data-automation-id="postedOn"], .posted, [class*="date" i]') || {}).innerText : '';
  const lines = (a.innerText || '').split('\n').map(s => s.trim()).filter(Boolean);
  const inner = a.querySelector('[class*="location" i], .body__secondary, [class*="secondary" i]');
  return { href: a.href, text: (lines[0] || a.getAttribute('aria-label') || '').replace(/\s+/g, ' '),
           location: ((loc || '').trim() || (inner ? inner.innerText.trim() : '') || (lines[1] || '')).replace(/\s+/g, ' '),
           posted: (posted || '').trim() };
})"""

_SEARCH_INPUTS = [
    'input[type="search"]', 'input[placeholder*="job" i]', 'input[placeholder*="keyword" i]',
    'input[aria-label*="job" i]', 'input[aria-label*="keyword" i]', 'input[name*="keyword" i]',
    'input[id*="keyword" i]', 'input[placeholder*="search" i]', 'input[aria-label*="search" i]',
    'input[data-automation-id="keywordSearchInput"]',
]
_SKIP_INPUT = re.compile(r"vendor|cookie|ot-|onetrust|newsletter|email|site-search|global", re.I)


def job_links(page, keyword: str | None, base_host: str) -> list[dict]:
    """Links that look like individual job postings (optionally containing the keyword words)."""
    out, seen = [], set()
    words = [w for w in re.split(r"\W+", (keyword or "").lower()) if len(w) > 1]
    for link in page.evaluate(_LINKS_JS):
        href, text = link["href"], link["text"]
        if not href.startswith("http") or href in seen or not (4 <= len(text) <= 140):
            continue
        host = urlsplit(href).netloc.lower()
        same_site = base_host and (host == base_host or host.endswith("." + base_host.split(".", 1)[-1]))
        if not (_JOBLIKE.search(href) or detect_ats(href)) or _NOT_JOB.search(href):
            continue
        if not (same_site or detect_ats(href)) or not _ID_LIKE.search(urlsplit(href).path):
            continue
        if words and not all(contains_term(text, w) for w in words):
            continue
        seen.add(href)
        out.append(link)
    return out


def find_search_box(page):
    for sel in _SEARCH_INPUTS:
        for el in page.query_selector_all(sel):
            try:
                ident = " ".join(filter(None, [el.get_attribute("id"), el.get_attribute("name"),
                                               el.get_attribute("class"), el.get_attribute("aria-label")]))
                if _SKIP_INPUT.search(ident) or not el.is_visible():
                    continue
                return el
            except Exception:
                continue
    return None


# ------------------------------------------------------------------ job page reader
_DETAIL_JS = r"""() => {
  const len = e => (e && e.innerText || '').length;
  // 1) known ATS description containers, in order of trust
  const specific = ['[data-automation-id="jobPostingDescription"]', '.job__description', '.posting-page .section-wrapper.page-full-width',
    '.iCIMS_JobContent', '#jobDescriptionText', '[class*="job-description" i]', '[id*="job-description" i]',
    '[class*="jobdescription" i]', '[id*="jobDescription"]'];
  for (const s of specific) {
    const all = [...document.querySelectorAll(s)].sort((a, b) => len(b) - len(a));
    if (all.length && len(all[0]) > 300) return { h1: ((document.querySelector('h1') || {}).innerText || '').trim(), description: all[0].innerText };
  }
  // 2) otherwise the biggest description-like block that is not the whole page
  const body = len(document.body);
  const pick = [...document.querySelectorAll('[class*="description" i], [id*="description" i], article, main, #content')]
    .map(e => ({ e, n: len(e) })).filter(x => x.n > 300 && x.n < body * 0.95).sort((a, b) => b.n - a.n);
  const best = pick[0] || { e: document.body };
  return { h1: ((document.querySelector('h1') || {}).innerText || '').trim(), description: best.e.innerText };
}"""


def read_job_page(ctx: RunContext, page, card: Card, company: str = "") -> JobDetail:
    ctx.goto(page, card.url)
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    posting = read_job_posting(page)
    f = posting_fields(posting) if posting else {}
    fb = page.evaluate(_DETAIL_JS)
    mode, loc = split_work_mode(f.get("location") or card.location)
    return JobDetail(
        url=card.url, title=f.get("title") or card.title or fb["h1"],
        company=f.get("company") or company or card.company, location=loc or card.location,
        work_mode=f.get("work_mode") or mode or card.work_mode, job_type=f.get("job_type", ""),
        posted_at=f.get("posted_at") or card.posted_at, posted_text=card.posted_text,
        description=f.get("description") or fb["description"].strip(), external_id=f.get("external_id", ""),
        apply_type="external",
    )


def _cards_from_links(links: list[dict], company: str) -> list[Card]:
    cards = []
    for l in links:
        mode, loc = split_work_mode(l.get("location", ""))
        cards.append(Card(url=l["href"], title=l["text"], company=company, location=loc, work_mode=mode,
                          posted_text=l.get("posted", ""), posted_at=parse_relative(l.get("posted", ""))))
    return cards


# ------------------------------------------------------------------ scrapers
class CareerPageScraper(BaseScraper):
    """One company's careers site."""

    key = "company_pages"
    name = "Company career pages"

    def __init__(self, company: dict):
        self.company = company
        self.portal_url: str | None = None  # resolved once per run

    def _resolve_portal(self, ctx: RunContext, page) -> str:
        if self.portal_url:
            return self.portal_url
        url = self.company["careers_url"]
        if detect_ats(url):
            self.portal_url = url
            return url
        ctx.goto(page, url)
        for link in page.evaluate(_LINKS_JS):
            if _PORTAL_LINK.search(link["text"]) and link["href"].startswith("http") and link["href"] != url:
                log.info(f"  following '{link['text'][:40]}' -> {link['href']}")
                self.portal_url = link["href"]
                return self.portal_url
        self.portal_url = url
        return url

    def search(self, ctx: RunContext, page, profile: dict, keyword: str, location: str) -> Iterator[Card]:
        name = self.company["name"]
        portal = self._resolve_portal(ctx, page)
        ats = detect_ats(portal)
        if ats:
            url = ats_search_url(ats, portal, keyword) or portal
            log.info(f"  {name}: {ats} search {url}")
            ctx.goto(page, url)
            try:
                page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass
            ctx.human_scroll(page, 2)
            # list-everything ATS pages: keep titles containing the keyword words
            links = job_links(page, keyword if ats in ("greenhouse", "lever", "ashby") else None, urlsplit(portal).netloc.lower())
            self.status = (f"ok ({ats}): {len(links)} jobs for '{keyword}'" if links
                           else f"no jobs found ({ats}) for '{keyword}'; check the careers URL or try another keyword")
            log.info(f"  {len(links)} job links")
            yield from _cards_from_links(links, name)
            return

        if page.url.rstrip("/") != portal.rstrip("/"):
            ctx.goto(page, portal)
        try:
            page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass
        box = find_search_box(page)
        host = urlsplit(page.url).netloc.lower()
        if box is not None:
            box.fill("")
            box.type(keyword, delay=60)
            box.press("Enter")
            ctx.sleep(3)
            try:
                page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass
            links = job_links(page, None, host) or job_links(page, keyword, host)
            self.status = (f"ok (search box on {host}): {len(links)} jobs for '{keyword}'" if links else
                           f"searched on {host} but found no job links; the portal may need you to log in "
                           f"('Log in now') or a custom adapter")
        else:
            links = job_links(page, keyword, host)
            needs_login = bool(re.search(r"\b(log ?in|sign ?in|register)\b", page.evaluate("document.body.innerText.slice(0,3000)"), re.I))
            self.status = (f"no job search box found on {host}"
                           + ("; the portal may need you to log in (use 'Log in to sites')" if needs_login else "")
                           + f"; matched {len(links)} links by title. An adapter may be needed.")
        log.info(f"  {self.status}")
        yield from _cards_from_links(links, name)

    def fetch_detail(self, ctx: RunContext, page, card: Card) -> JobDetail:
        return read_job_page(ctx, page, card, self.company["name"])


class CustomSiteScraper(BaseScraper):
    """A job site added on Companies & Sites with a search URL template ({keyword}, {location})."""

    def __init__(self, site: dict):
        self.site = site
        self.key = site["key"]
        self.name = site["name"]

    def search(self, ctx: RunContext, page, profile: dict, keyword: str, location: str) -> Iterator[Card]:
        tpl = self.site["search_url"] or ""
        url = tpl.replace("{keyword}", quote_plus(keyword)).replace("{location}", quote_plus(location or ""))
        log.info(f"{self.name} search: {url}")
        ctx.goto(page, url)
        try:
            page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass
        ctx.human_scroll(page, 2)
        links = job_links(page, None, urlsplit(page.url).netloc.lower())
        log.info(f"  {len(links)} job links")
        yield from _cards_from_links(links, "")

    def fetch_detail(self, ctx: RunContext, page, card: Card) -> JobDetail:
        return read_job_page(ctx, page, card)
