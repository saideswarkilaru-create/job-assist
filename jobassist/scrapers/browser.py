"""Persistent browser profile in browser-profile/. You log in by hand once; cookies stay there.

Uses your installed Google Chrome (or Edge) through Playwright's `channel` option: signed,
auto-updated, and it opens on PCs where Playwright's bundled Chromium is blocked from starting.
No stealth flags or fingerprint tricks: it is a normal visible browser window.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager

from .. import paths

log = logging.getLogger("jobassist")

CHANNELS = ["chrome", "msedge", "chromium"]  # "chromium" = Playwright's bundled build


def _launch(p, channel: str, headless: bool):
    kw = dict(headless=headless, no_viewport=True, args=["--start-maximized"], accept_downloads=True)
    if channel != "chromium":
        kw["channel"] = channel
    return p.chromium.launch_persistent_context(str(paths.BROWSER_PROFILE), **kw)


@contextmanager
def open_browser(headless: bool = False, timeout_sec: int = 45, channel: str = "chrome"):
    from playwright.sync_api import sync_playwright

    paths.ensure_dirs()
    order = [channel] + [c for c in CHANNELS if c != channel]
    with sync_playwright() as p:
        ctx, errors = None, []
        for ch in order:
            try:
                ctx = _launch(p, ch, headless)
                if ch != channel:
                    log.warning(f"Browser '{channel}' did not start; using '{ch}' instead.")
                break
            except Exception as e:
                errors.append(f"{ch}: {str(e).splitlines()[0]}")
        if ctx is None:
            raise RuntimeError("Could not start any browser. " + " | ".join(errors))
        ctx.set_default_timeout(timeout_sec * 1000)
        try:
            yield ctx
        finally:
            try:
                ctx.close()
            except Exception:
                pass
