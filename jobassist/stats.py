"""Stats: which profiles, sites and search keywords actually lead to responses and interviews.

Definitions (recruiting-funnel standard):
  found      jobs collected (one per unique job, cross-board duplicates counted once)
  matched    jobs that passed a profile's screening
  tailored   jobs with a tailored resume
  applied    applications logged
  responses  applications that got any reply (Screening, Interview, Offer or Rejected)
  interviews applications that reached Interview at any point (kept even if later rejected or offered)
  offers     applications with status Offer
Rates are per application: response rate = responses / applied, interview rate = interviews / applied.
"""
from __future__ import annotations

import re

_RESPONDED = "a.status IN ('Screening', 'Interview', 'Offer', 'Rejected')"
_INTERVIEW = "(a.status IN ('Interview', 'Offer') OR a.history LIKE '%\"Interview\"%')"
_OFFER = "a.status = 'Offer'"


def _rate(n: int, d: int) -> float | None:
    return round(100 * n / d, 1) if d else None


def _row(name, found, matched, applied, responses, interviews, offers=0, **extra) -> dict:
    return {"name": name, "found": found, "matched": matched, "applied": applied, "responses": responses,
            "interviews": interviews, "offers": offers, "response_rate": _rate(responses, applied),
            "interview_rate": _rate(interviews, applied), **extra}


def funnel(conn) -> list[dict]:
    q = lambda sql: conn.execute(sql).fetchone()[0]
    steps = [
        ("Found", q("SELECT COUNT(*) FROM jobs WHERE duplicate_of IS NULL")),
        ("Matched", q("SELECT COUNT(DISTINCT h.job_id) FROM job_hits h JOIN jobs j ON j.id = h.job_id "
                      "WHERE h.matched = 1 AND j.duplicate_of IS NULL")),
        ("Tailored", q("SELECT COUNT(*) FROM jobs WHERE tailored_at IS NOT NULL")),
        ("Applied", q("SELECT COUNT(*) FROM applications")),
        ("Responses", q(f"SELECT COUNT(*) FROM applications a WHERE {_RESPONDED}")),
        ("Interviews", q(f"SELECT COUNT(*) FROM applications a WHERE {_INTERVIEW}")),
        ("Offers", q(f"SELECT COUNT(*) FROM applications a WHERE {_OFFER}")),
    ]
    return [{"step": s, "count": n} for s, n in steps]


def by_profile(conn) -> list[dict]:
    rows = conn.execute(f"""
        SELECT p.name,
          (SELECT COUNT(DISTINCT h.job_id) FROM job_hits h WHERE h.profile_id = p.id) AS found,
          (SELECT COUNT(DISTINCT h.job_id) FROM job_hits h WHERE h.profile_id = p.id AND h.matched = 1) AS matched,
          COUNT(DISTINCT a.id) AS applied,
          COUNT(DISTINCT CASE WHEN {_RESPONDED} THEN a.id END) AS responses,
          COUNT(DISTINCT CASE WHEN {_INTERVIEW} THEN a.id END) AS interviews,
          COUNT(DISTINCT CASE WHEN {_OFFER} THEN a.id END) AS offers
        FROM profiles p
        LEFT JOIN job_hits h2 ON h2.profile_id = p.id AND h2.matched = 1
        LEFT JOIN applications a ON a.job_id = h2.job_id
        GROUP BY p.id ORDER BY applied DESC, matched DESC""").fetchall()
    return [_row(*r) for r in rows]


SITE_NAMES = {"dice": "Dice", "linkedin": "LinkedIn", "indeed": "Indeed", "naukri": "Naukri",
              "company_pages": "Company career pages"}


def by_site(conn) -> list[dict]:
    rows = conn.execute(f"""
        SELECT j.site,
          COUNT(DISTINCT j.id) AS found,
          COUNT(DISTINCT CASE WHEN EXISTS (SELECT 1 FROM job_hits h WHERE h.job_id = j.id AND h.matched = 1) THEN j.id END),
          COUNT(DISTINCT a.id),
          COUNT(DISTINCT CASE WHEN {_RESPONDED} THEN a.id END),
          COUNT(DISTINCT CASE WHEN {_INTERVIEW} THEN a.id END),
          COUNT(DISTINCT CASE WHEN {_OFFER} THEN a.id END)
        FROM jobs j LEFT JOIN applications a ON a.job_id = j.id
        WHERE j.duplicate_of IS NULL
        GROUP BY j.site ORDER BY 4 DESC, 3 DESC""").fetchall()
    return [_row(SITE_NAMES.get(r[0], r[0]), *r[1:]) for r in rows]


def by_keyword(conn) -> list[dict]:
    rows = conn.execute(f"""
        SELECT h.keyword,
          COUNT(DISTINCT h.job_id) AS found,
          COUNT(DISTINCT CASE WHEN h.matched = 1 THEN h.job_id END) AS matched,
          COUNT(DISTINCT CASE WHEN h.matched = 1 THEN a.id END) AS applied,
          COUNT(DISTINCT CASE WHEN h.matched = 1 AND {_RESPONDED} THEN a.id END),
          COUNT(DISTINCT CASE WHEN h.matched = 1 AND {_INTERVIEW} THEN a.id END),
          COUNT(DISTINCT CASE WHEN h.matched = 1 AND {_OFFER} THEN a.id END),
          ROUND(AVG(CASE WHEN h.matched = 1 THEN j.match_score END), 0) AS avg_score
        FROM job_hits h JOIN jobs j ON j.id = h.job_id LEFT JOIN applications a ON a.job_id = h.job_id
        WHERE h.keyword != ''
        GROUP BY lower(h.keyword) ORDER BY applied DESC, matched DESC LIMIT 30""").fetchall()
    return [_row(*r[:7], avg_score=r[7]) for r in rows]


_REASON_GROUPS = [
    (r"^visa", "Visa / sponsorship"),
    (r"clearance", "Security clearance"),
    (r"^asks \d+\+ years", "Too many years asked"),
    (r"excluded", "Excluded word"),
    (r"must-include", "Missing must-include word"),
    (r"-level$", "Seniority level"),
    (r"work mode", "Work mode"),
    (r"posted", "Too old"),
]


def hidden_reasons(conn) -> list[dict]:
    counts: dict[str, int] = {}
    for (reason,) in conn.execute("SELECT reason FROM job_hits WHERE matched = 0"):
        label = next((name for rx, name in _REASON_GROUPS if re.search(rx, reason or "", re.I)), "Other")
        counts[label] = counts.get(label, 0) + 1
    return [{"reason": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]


def weekly(conn, weeks: int = 12) -> list[dict]:
    rows = dict(conn.execute("""
        SELECT strftime('%Y-%W', applied_at), COUNT(*) FROM applications
        WHERE applied_at >= date('now', ?) GROUP BY 1""", (f"-{weeks * 7} days",)).fetchall())
    out = []
    for i in range(weeks - 1, -1, -1):
        wk, start = conn.execute("SELECT strftime('%Y-%W', date('now', ?)), date('now', ?, 'weekday 1', '-7 days')",
                                 (f"-{i * 7} days", f"-{i * 7} days")).fetchone()
        out.append({"week": wk, "start": start, "applied": rows.get(wk, 0)})
    return out


def scores(conn) -> dict:
    q = lambda where: conn.execute(f"SELECT ROUND(AVG(j.match_score), 0) FROM applications a JOIN jobs j ON j.id = a.job_id "
                                   f"WHERE j.match_score IS NOT NULL AND {where}").fetchone()[0]
    return {"applied": q("1 = 1"), "interviewed": q(_INTERVIEW), "no_response": q("a.status IN ('Applied', 'No response')")}


def summary(conn, settings: dict) -> dict:
    from . import repo

    apps = conn.execute(f"""SELECT COUNT(*), SUM(CASE WHEN {_RESPONDED} THEN 1 ELSE 0 END),
                                   SUM(CASE WHEN {_INTERVIEW} THEN 1 ELSE 0 END) FROM applications a""").fetchone()
    applied, responses, interviews = apps[0] or 0, apps[1] or 0, apps[2] or 0
    return {
        "applied": applied, "responses": responses, "interviews": interviews,
        "response_rate": _rate(responses, applied), "interview_rate": _rate(interviews, applied),
        "applied_today": repo.applied_today(conn), "daily_cap": int(settings.get("daily_apply_cap", 15)),
        "follow_up_due": repo.application_counts(conn)["follow_up_due"],
        "applied_7d": conn.execute("SELECT COUNT(*) FROM applications WHERE applied_at >= date('now', '-6 days')").fetchone()[0],
    }


def all_stats(conn, settings: dict) -> dict:
    return {"summary": summary(conn, settings), "funnel": funnel(conn), "profiles": by_profile(conn),
            "sites": by_site(conn), "keywords": by_keyword(conn), "hidden": hidden_reasons(conn),
            "weekly": weekly(conn), "scores": scores(conn)}
