# Company adapters (Phase 2)

Most career pages are handled by the generic career-page scraper. When a company's page needs
special handling, Claude writes a small adapter here (one file per company, e.g. `tcs_usa.py`)
and sets the company's `adapter` field on the Companies & Sites page.

An adapter subclasses `jobassist.scrapers.base.BaseScraper` and implements `search()` and
`fetch_detail()`. It must follow the same rules: normal pages only, go through `ctx.goto()`,
no captcha solving, no hidden APIs.
