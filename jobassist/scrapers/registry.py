"""Source key -> scraper. Job boards, custom sites, company pages and company adapters."""
from __future__ import annotations

import importlib.util
import logging
import re

from .. import paths
from .base import BaseScraper
from .careers import CareerPageScraper, CustomSiteScraper
from .dice import DiceScraper
from .indeed import IndeedScraper
from .linkedin import LinkedInScraper
from .naukri import NaukriScraper

log = logging.getLogger("jobassist")

_BOARDS: dict[str, type[BaseScraper]] = {
    DiceScraper.key: DiceScraper,
    LinkedInScraper.key: LinkedInScraper,
    IndeedScraper.key: IndeedScraper,
    NaukriScraper.key: NaukriScraper,
}

# Login pages opened by "Log in to sites" (and used by saved-login auto sign-in).
LOGIN_URLS = {k: cls.login_url for k, cls in _BOARDS.items()}


def get_scraper(site_key: str, site: dict | None = None) -> BaseScraper | None:
    cls = _BOARDS.get(site_key)
    if cls:
        return cls()
    if site and site.get("kind") == "custom" and site.get("search_url"):
        return CustomSiteScraper(site)
    return None


def implemented() -> list[str]:
    return list(_BOARDS) + ["company_pages"]


def load_adapter(name: str):
    """Load adapters/<name>.py and return its `Adapter` class."""
    if not re.fullmatch(r"[a-z0-9_]+", name or ""):
        raise ValueError(f"Bad adapter name: {name!r}")
    path = paths.ADAPTERS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"adapters.{name}", path)
    if not spec or not path.exists():
        raise FileNotFoundError(f"adapters/{name}.py not found")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Adapter


def company_scraper(company: dict) -> BaseScraper:
    if company.get("adapter"):
        try:
            return load_adapter(company["adapter"])(company)
        except Exception as e:
            log.warning(f"Adapter '{company['adapter']}' failed to load ({e}); using the generic scraper.")
    return CareerPageScraper(company)
