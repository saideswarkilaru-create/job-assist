"""Site logins. Two modes per site or company portal (Companies & Sites page):

  manual (default)  You sign in yourself in the app's browser window; cookies are kept in browser-profile/.
  saved             You enter username + password once in the app. The PASSWORD is stored only in
                    Windows Credential Manager (keyring, encrypted by Windows for your user account).
                    The app fills the site's login form when a login page appears.

Rules: passwords are never written to the database, logs, files or API responses. Two-step
verification codes and captchas are always left to you.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit

from . import repo

log = logging.getLogger("jobassist")
SERVICE = "JobAssist"

HOST_KEYS = {"linkedin.com": "linkedin", "dice.com": "dice", "indeed.com": "indeed", "naukri.com": "naukri"}


def _keyring():
    import keyring
    return keyring


# ------------------------------------------------------------------ storage
def list_logins(conn) -> dict[str, dict]:
    return {r["login_key"]: dict(r) for r in conn.execute("SELECT * FROM logins")}


def save_login(conn, key: str, mode: str, username: str = "", password: str | None = None) -> None:
    if mode not in ("manual", "saved"):
        raise ValueError("mode must be manual or saved")
    username = (username or "").strip()
    if mode == "saved":
        if not username:
            raise ValueError("Enter your username / email")
        if password:
            _keyring().set_password(f"{SERVICE}:{key}", username, password)
        elif not has_password(conn, key, username):
            raise ValueError("Enter your password")
    else:
        forget_password(conn, key)
    old = list_logins(conn).get(key)
    if old and old["username"] and old["username"] != username:
        _delete_secret(key, old["username"])
    conn.execute("""INSERT INTO logins(login_key, mode, username) VALUES(?,?,?)
                    ON CONFLICT(login_key) DO UPDATE SET mode = excluded.mode, username = excluded.username,
                    updated_at = datetime('now')""", (key, mode, username if mode == "saved" else ""))
    conn.commit()


def has_password(conn, key: str, username: str | None = None) -> bool:
    if username is None:
        row = list_logins(conn).get(key)
        username = row["username"] if row else ""
    if not username:
        return False
    try:
        return _keyring().get_password(f"{SERVICE}:{key}", username) is not None
    except Exception:
        return False


def _delete_secret(key: str, username: str) -> None:
    try:
        _keyring().delete_password(f"{SERVICE}:{key}", username)
    except Exception:
        pass


def forget_password(conn, key: str) -> None:
    row = list_logins(conn).get(key)
    if row and row["username"]:
        _delete_secret(key, row["username"])


def credentials(conn, key: str) -> tuple[str, str] | None:
    row = list_logins(conn).get(key)
    if not row or row["mode"] != "saved" or not row["username"]:
        return None
    pw = _keyring().get_password(f"{SERVICE}:{key}", row["username"])
    return (row["username"], pw) if pw else None


def key_for_url(conn, url: str) -> str | None:
    host = urlsplit(url).netloc.lower()
    for h, k in HOST_KEYS.items():
        if host == h or host.endswith("." + h):
            return k
    for c in repo.list_companies(conn):
        for u in (c["careers_url"],):
            ch = urlsplit(u).netloc.lower()
            if ch and (host == ch or host.split(".", 1)[-1] == ch.split(".", 1)[-1]):
                return f"company_{c['id']}"
    return None


# ------------------------------------------------------------------ form filling
_USER_SEL = ['input[autocomplete="username"]', 'input[type="email"]', '#username', '#usernameField',
             'input[name="email"]', 'input[name*="user" i]', 'input[name*="login" i]', 'input[id*="email" i]',
             'input[id*="user" i]']
_PASS_SEL = ['input[type="password"]']
_SUBMIT = re.compile(r"^(sign ?in|log ?in|continue|next|submit|login)$", re.I)


def _first_visible(page, selectors):
    for sel in selectors:
        for el in page.query_selector_all(sel):
            try:
                if el.is_visible() and el.is_enabled():
                    return el
            except Exception:
                continue
    return None


def _click_submit(page) -> bool:
    for el in page.query_selector_all('button, input[type="submit"], [role="button"]'):
        try:
            label = (el.inner_text() or el.get_attribute("value") or "").strip()
            if _SUBMIT.match(label) and el.is_visible():
                el.click()
                return True
        except Exception:
            continue
    return False


def auto_login(ctx, page, key: str) -> bool:
    """Fill the login form with saved credentials. Returns True if a submit happened."""
    creds = credentials(ctx.conn, key)
    if not creds:
        return False
    username, password = creds
    log.info(f"Signing in to {key} with your saved login ({username}).")
    user = _first_visible(page, _USER_SEL)
    if user:
        user.fill(username)
        ctx.sleep(0.8)
    pw = _first_visible(page, _PASS_SEL)
    if pw is None and user is not None:  # two-step forms: email first, then password
        if not _click_submit(page):
            user.press("Enter")
        ctx.sleep(3)
        pw = _first_visible(page, _PASS_SEL)
    if pw is None:
        log.info("  password field not shown (the site may email you a code); please finish in the window.")
        return False
    pw.fill(password)
    ctx.sleep(0.6)
    if not _click_submit(page):
        pw.press("Enter")
    ctx.sleep(5)
    return True
