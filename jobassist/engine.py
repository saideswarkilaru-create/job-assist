"""Search orchestration: one profile -> its sources -> keywords x locations -> screen -> save.

Every source (job board, company career page, custom adapter) goes through the same pipeline:
dedupe by URL, cheap title screen, fetch detail once, recruiter signals (jd_parse.inspect),
cross-board duplicate link, profile + candidate screen, job_hit verdict.
"""
from __future__ import annotations

import logging
import re

from . import filters, jd_parse, repo
from .scrapers.base import Blocked, BudgetExhausted, Card, RunContext
from .scrapers.registry import company_scraper, get_scraper
from .textutil import normalize_url

log = logging.getLogger("jobassist")


class _ProfileDone(Exception):
    pass


class _SourceDone(Exception):
    pass


def run_profile(ctx: RunContext, browser, profile: dict) -> dict:
    counts = {"seen": 0, "new": 0, "matched": 0}
    if not profile["keywords"]:
        log.warning(f"Profile '{profile['name']}' has no keywords; skipped.")
        return counts
    seen_urls: set[str] = set()
    locations = profile["locations"] or [""]
    log.info(f"=== Profile '{profile['name']}': {len(profile['keywords'])} keyword(s) x "
             f"{len(locations)} location(s), sources {profile['sites']}, max {profile['max_jobs']} new matches")
    sources = []
    for site_key in profile["sites"]:
        site = repo.get_site(ctx.conn, site_key)
        if not site or not site["enabled"]:
            log.info(f"Source '{site_key}' is turned off on Companies & Sites; skipped.")
            continue
        scraper = None if site_key == "company_pages" else get_scraper(site_key, site)
        if site_key != "company_pages" and scraper is None:
            log.info(f"No scraper for '{site['name']}' yet; skipped.")
            continue
        sources.append((site_key, site, scraper))
    # Fair share: each source may fill at most its part of max_jobs, so one board can't crowd out the rest.
    quota = max(1, -(-int(profile["max_jobs"]) // max(1, len(sources))))
    state = dict(ctx=ctx, profile=profile, seen=seen_urls, counts=counts, quota=quota, source_matched=0)
    try:
        for site_key, site, scraper in sources:
            state["source_matched"] = 0
            try:
                if site_key == "company_pages":
                    _search_companies(state, browser)
                else:
                    _with_page(browser, lambda page: _search_board(state, page, scraper, site_key, locations), site["name"])
            except _SourceDone:
                log.info(f"{site['name']}: reached its share ({quota}) of this profile's matches.")
    except _ProfileDone:
        log.info(f"Reached {profile['max_jobs']} new matches for '{profile['name']}'.")
    except BudgetExhausted:
        log.info("Reached the per-run limit of job pages (Settings > Max job pages opened per run).")
        raise
    return counts


def _with_page(browser, fn, label: str):
    page = browser.new_page()
    try:
        fn(page)
    except (_SourceDone, _ProfileDone):
        raise
    except Blocked as e:
        log.warning(f"{label}: {e}. Skipping it for this profile.")
    finally:
        try:
            page.close()
        except Exception:
            pass


def _search_board(state, page, scraper, site_key, locations):
    ctx = state["ctx"]
    for keyword in state["profile"]["keywords"]:
        for location in locations:
            for card in scraper.search(ctx, page, state["profile"], keyword, location):
                _consider(state, page, scraper, site_key, card, keyword, location)
            ctx.delay()


def _search_companies(state, browser):
    ctx = state["ctx"]
    companies = [c for c in repo.list_companies(ctx.conn) if c["enabled"]]
    if not companies:
        log.info("No companies are turned on (Companies & Sites).")
        return
    for company in companies:
        scraper = company_scraper(company)

        def run(page, company=company, scraper=scraper):
            found = 0
            for keyword in state["profile"]["keywords"]:
                for card in scraper.search(ctx, page, state["profile"], keyword, ""):
                    found += 1
                    if not card.company:
                        card.company = company["name"]
                    if not _location_ok(state["profile"], card.location):
                        log.info(f"  skip  {card.title[:70]}  (location {card.location})")
                        continue
                    _consider(state, page, scraper, "company_pages", card, keyword, "")
                ctx.delay()
            repo.set_company_status(ctx.conn, company["id"], scraper.status or f"ok: {found} job links found")

        log.info(f"--- {company['name']} ({company['careers_url']})")
        _with_page(browser, run, company["name"])


def _location_ok(profile: dict, location: str) -> bool:
    """Career pages list every location; keep jobs in the profile's places (or remote, or unknown)."""
    if not profile["locations"] or not location:
        return True
    loc = location.lower()
    if "remote" in loc and (not profile["work_modes"] or "Remote" in profile["work_modes"]):
        return True
    for want in profile["locations"]:
        city = re.split(r"[,;]", want.lower())[0].strip()
        if city == "remote" and "remote" in loc:
            return True
        if city and city in loc:
            return True
    return False


def _consider(state, page, scraper, site_key: str, card: Card, keyword: str, location: str) -> None:
    ctx, profile, counts = state["ctx"], state["profile"], state["counts"]
    url = normalize_url(card.url)
    if url in state["seen"]:
        return
    state["seen"].add(url)
    counts["seen"] += 1
    repo.bump_run(ctx.conn, ctx.run_id, seen=1)

    reason = filters.title_excluded(profile, card.title)
    if reason:
        log.info(f"  skip  {card.title[:70]}  ({reason})")
        return

    job = repo.get_job_by_url(ctx.conn, url)
    if job:
        repo.touch_job(ctx.conn, job["id"])
        prev = repo.get_hit(ctx.conn, job["id"], profile["id"])
        if prev and prev["matched"]:
            return
    else:
        ctx.use_detail_page()
        ctx.delay(0.6)
        try:
            d = scraper.fetch_detail(ctx, page, card)
            data = {**d.as_row(), "url": url, "site": site_key}
            data["posted_at"] = data.get("posted_at") or card.posted_at
            data["work_mode"] = data.get("work_mode") or card.work_mode
        except Blocked as e:
            data = {"url": url, "site": site_key, "title": card.title, "company": card.company,
                    "location": card.location, "posted_text": card.posted_text, "posted_at": card.posted_at,
                    "status": "Manual", "status_note": f"Open by hand: {e}"}
            log.warning(f"  manual {card.title[:70]}  ({e})")
        data.update(jd_parse.inspect(data))
        jid = repo.insert_job(ctx.conn, data, ctx.run_id)
        counts["new"] += 1
        repo.bump_run(ctx.conn, ctx.run_id, new=1)
        job = repo.get_job(ctx.conn, jid)
        if job["duplicate_of"]:
            log.info(f"  same job already found on another site (#{job['duplicate_of']}): {job['title'][:60]}")

    if job["status"] == "Manual" and not job["description"]:
        matched, why = True, "needs manual check"
    else:
        matched, why = filters.evaluate(profile, job, ctx.s)
    target_id = job["duplicate_of"] or job["id"]
    if target_id != job["id"]:
        repo.upsert_hit(ctx.conn, job["id"], profile["id"], ctx.run_id, keyword, location, site_key, matched, why)
        prev = repo.get_hit(ctx.conn, target_id, profile["id"])
        if prev and prev["matched"]:
            return  # same job already on your list from another site
    repo.upsert_hit(ctx.conn, target_id, profile["id"], ctx.run_id, keyword, location, site_key, matched, why)
    if matched:
        counts["matched"] += 1
        repo.bump_run(ctx.conn, ctx.run_id, matched=1)
        log.info(f"  MATCH {job['title'][:70]} @ {job['company'][:30]}")
        state["source_matched"] += 1
        if counts["matched"] >= int(profile["max_jobs"]):
            raise _ProfileDone()
        if state["source_matched"] >= state["quota"]:
            raise _SourceDone()
    else:
        log.info(f"  skip  {job['title'][:70]}  ({why})")
