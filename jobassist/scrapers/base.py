"""Shared scraper plumbing: run context, pacing, captcha/login detection, data classes.

Safety rules enforced here for every site:
- Human-like pacing between actions (settings: delay_min_sec / delay_max_sec).
- Captcha, login wall or block page -> pause and ask the user to handle it in the visible
  browser window. Nothing here tries to solve or bypass anything.
- Hard budget on job pages opened per run.
"""
from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass, field
from typing import Iterator

from .. import repo

log = logging.getLogger("jobassist")


class Cancelled(Exception):
    pass


class Blocked(Exception):
    """The site showed a captcha / login wall / block page that was not cleared."""


class BudgetExhausted(Exception):
    pass


@dataclass
class Card:
    """One result row on a search page."""
    url: str
    title: str = ""
    company: str = ""
    location: str = ""
    posted_text: str = ""
    posted_at: str = ""
    work_mode: str = ""
    external_id: str = ""
    source_url: str = ""  # the search page this card came from


@dataclass
class JobDetail:
    url: str
    title: str = ""
    company: str = ""
    location: str = ""
    work_mode: str = ""
    job_type: str = ""
    posted_at: str = ""
    posted_text: str = ""
    description: str = ""
    external_id: str = ""
    applicants: str = ""      # e.g. "75 applicants" (LinkedIn)
    apply_type: str = ""      # easy_apply | external | ""
    extra: dict = field(default_factory=dict)

    def as_row(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "extra"}
        return d


_CAPTCHA_FRAMES = re.compile(r"recaptcha|hcaptcha|challenges\.cloudflare\.com|turnstile|arkoselabs|funcaptcha|captcha", re.I)
_CAPTCHA_TEXT = re.compile(r"verify(ing)? (that )?you are (a )?human|are you a robot|unusual traffic|press (and|&) hold|"
                           r"checking your browser|complete the security check|i'?m not a robot|"
                           r"checking if the site connection is secure|review the security of your connection", re.I)
_CAPTCHA_TITLE = re.compile(r"^(just a moment|attention required|security check|verify|are you a robot)", re.I)
_LOGIN_URL = re.compile(r"/(login|signin|sign-in|uas/login|authwall|checkpoint|nlogin|auth)\b", re.I)
_BLOCK_TITLE = re.compile(r"^(access denied|403|forbidden|blocked|attention required)", re.I)

_PAGE_STATE_JS = """() => ({
  url: location.href,
  title: document.title || '',
  text: (document.body ? document.body.innerText : '').slice(0, 6000),
  frames: [...document.querySelectorAll('iframe')].map(f => f.src || '').join(' ')
})"""


def detect_block(page) -> str | None:
    """Return 'captcha' | 'login' | 'blocked' | None for the current page."""
    try:
        st = page.evaluate(_PAGE_STATE_JS)
    except Exception:
        return None
    if _CAPTCHA_TITLE.search(st["title"].strip()):
        return "captcha"
    if _CAPTCHA_FRAMES.search(st["frames"]) and len(st["text"]) < 4000:
        return "captcha"
    if _CAPTCHA_TEXT.search(st["text"]) and len(st["text"]) < 4000:
        return "captcha"
    if _LOGIN_URL.search(st["url"].split("?")[0]):
        return "login"
    if _BLOCK_TITLE.search(st["title"].strip()):
        return "blocked"
    return None


class RunContext:
    """Everything a scraper needs from the current run, without knowing about the DB or UI."""

    def __init__(self, conn, run_id: int, settings: dict):
        self.conn = conn
        self.run_id = run_id
        self.s = settings
        self.detail_budget = int(settings["max_detail_pages_per_run"])

    # ---- control
    def check_cancel(self) -> None:
        if repo.cancel_requested(self.conn, self.run_id):
            raise Cancelled()

    def status(self, status: str, message: str = "") -> None:
        repo.update_run(self.conn, self.run_id, status=status, message=message)

    def sleep(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.check_cancel()
            time.sleep(min(0.5, max(0.0, end - time.monotonic())))

    def delay(self, factor: float = 1.0) -> None:
        lo, hi = float(self.s["delay_min_sec"]), float(self.s["delay_max_sec"])
        self.sleep(random.uniform(lo, max(lo, hi)) * factor)

    def use_detail_page(self) -> None:
        if self.detail_budget <= 0:
            raise BudgetExhausted()
        self.detail_budget -= 1

    # ---- navigation with block handling
    def goto(self, page, url: str) -> None:
        self.check_cancel()
        page.goto(url, wait_until="domcontentloaded", timeout=int(self.s["page_timeout_sec"]) * 1000)
        self.sleep(random.uniform(1.0, 2.0))
        kind = detect_block(page)
        if kind:
            self.wait_for_user(page, kind)

    def wait_for_user(self, page, kind: str) -> None:
        """Pause until the user clears a captcha / login in the visible window, or give up."""
        site = re.sub(r"^https?://(www\.)?", "", page.url).split("/")[0]
        what = {"captcha": "a captcha", "login": "a login page", "blocked": "a block page"}[kind]
        if kind == "captcha":
            # Browser checks ("Just a moment...") usually clear by themselves in a few seconds.
            for _ in range(8):
                self.sleep(2)
                if detect_block(page) is None:
                    return
        if kind == "login":
            from .. import auth
            key = auth.key_for_url(self.conn, page.url)
            if key and auth.auto_login(self, page, key) and detect_block(page) is None:
                log.info("Signed in with your saved login.")
                return
        if self.s.get("headless"):
            raise Blocked(f"{site} showed {what}; turn off 'Hide the browser window' to handle it yourself")
        minutes = int(self.s["user_wait_minutes"])
        msg = (f"{site} is showing {what}. Please handle it in the browser window "
               f"(the app never solves captchas). Waiting up to {minutes} min.")
        log.warning(msg)
        self.status("waiting_user", msg)
        try:
            page.bring_to_front()
        except Exception:
            pass
        deadline = time.monotonic() + minutes * 60
        while time.monotonic() < deadline:
            self.sleep(5)
            if detect_block(page) is None:
                log.info("Cleared, continuing.")
                self.status("running", "")
                return
        self.status("running", "")
        raise Blocked(f"{site} still showed {what} after {minutes} min")

    def human_scroll(self, page, steps: int = 3) -> None:
        for _ in range(steps):
            try:
                page.mouse.wheel(0, random.randint(300, 800))
            except Exception:
                return
            self.sleep(random.uniform(0.4, 1.2))


class BaseScraper:
    """Implement search() and fetch_detail() for a site. Both must go through ctx.goto()."""

    key = ""
    name = ""
    login_url = ""
    status = ""  # short human-readable outcome of the last search (shown on Companies & Sites)

    def search(self, ctx: RunContext, page, profile: dict, keyword: str, location: str) -> Iterator[Card]:
        raise NotImplementedError

    def fetch_detail(self, ctx: RunContext, page, card: Card) -> JobDetail:
        raise NotImplementedError
