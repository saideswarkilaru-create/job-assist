"""URL normalization, HTML-to-text, keyword matching and date helpers."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query params that only track where a click came from; they must not break dedupe.
_TRACKING = re.compile(r"^(utm_.*|searchlink|searchid|src|source|ref|refid|trk|trackingid|"
                       r"from|position|pagenum|gclid|fbclid|mc_.*|_ga|sid|session.*)$", re.I)
# Sites where the path alone identifies the job.
_PATH_ONLY_HOSTS = ("dice.com",)


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/") or "/"
    if any(host.endswith(h) for h in _PATH_ONLY_HOSTS):
        query = ""
    else:
        kept = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING.match(k))
        query = urlencode(kept)
    return urlunsplit(("https" if parts.scheme in ("http", "https") else parts.scheme, host, path, query, ""))


class _TextExtractor(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            self.parts.append("\n- ")
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def html_to_text(html: str) -> str:
    if not html:
        return ""
    p = _TextExtractor()
    p.feed(html)
    text = "".join(p.parts).replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def term_regex(term: str) -> re.Pattern:
    """Whole-word, case-insensitive match that also works for terms like C++ or .NET."""
    return re.compile(rf"(?<![\w]){re.escape(term.strip())}(?![\w])", re.I)


def contains_term(text: str, term: str) -> bool:
    return bool(term.strip()) and bool(term_regex(term).search(text or ""))


def parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.strptime(value[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return s[:max_len].rstrip("_") or "item"


_REL = re.compile(r"(\d+)\+?\s*(min|minute|h|hr|hour|d|day|w|wk|week|mo|month)s?\b", re.I)
_REL_UNIT = {"min": 1 / 1440, "minute": 1 / 1440, "h": 1 / 24, "hr": 1 / 24, "hour": 1 / 24, "d": 1, "day": 1,
             "w": 7, "wk": 7, "week": 7, "mo": 30, "month": 30}


def parse_relative(text: str, now: datetime | None = None) -> str:
    """'2 hours ago', '3d ago', 'Today', 'Just posted', '30+ days ago' -> ISO UTC timestamp, or ''."""
    from datetime import timedelta

    now = now or datetime.now(timezone.utc)
    t = (text or "").strip().lower()
    if not t:
        return ""
    if re.search(r"just (now|posted)|moments? ago|today|active today|few hours", t):
        return now.isoformat(timespec="seconds")
    if "yesterday" in t:
        return (now - timedelta(days=1)).isoformat(timespec="seconds")
    m = _REL.search(t)
    if not m:
        return ""
    days = int(m.group(1)) * _REL_UNIT[m.group(2).lower()]
    return (now - timedelta(days=days)).isoformat(timespec="seconds")


_MODE = re.compile(r"\b(remote|hybrid|on[- ]?site|in[- ]office)\b", re.I)


def split_work_mode(text: str) -> tuple[str, str]:
    """'Hybrid work in Southlake, TX' -> ('Hybrid', 'Southlake, TX'); 'Remote' -> ('Remote', 'Remote')."""
    t = re.sub(r"\s+", " ", text or "").strip()
    m = _MODE.search(t)
    if not m:
        return "", t
    word = m.group(1).lower()
    mode = "Remote" if word == "remote" else "Hybrid" if word == "hybrid" else "On-site"
    rest = re.sub(r"^(remote|hybrid|on[- ]?site|in[- ]office)( work)?( in| -|:)?\s*", "", t, flags=re.I).strip(" ,-•(")
    rest = re.sub(r"\(?(remote|hybrid|on[- ]?site)\)?$", "", rest, flags=re.I).strip(" ,-•(")
    return mode, rest or ("Remote" if mode == "Remote" else "")
