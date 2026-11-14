"""Skills library + extractor for the built-in matcher (offline, deterministic)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

LIBRARY_FILE = Path(__file__).parent / "data" / "skills.yaml"

# How much each category counts toward the match score (recruiter view: core tech > process tools).
CATEGORY_WEIGHT = {"methods": 0.5, "security": 0.8, "custom": 1.0}


@dataclass(frozen=True)
class Skill:
    name: str
    category: str
    pattern: re.Pattern

    @property
    def weight(self) -> float:
        return CATEGORY_WEIGHT.get(self.category, 1.0)


def _compile(name: str, aliases: list[str]) -> re.Pattern:
    ci, cs = [name], []
    for a in aliases or []:
        a = str(a).strip()
        if not a:
            continue
        (cs if a.startswith("=") else ci).append(a.lstrip("="))
    # Longest first so "Spring Boot" wins over "Spring" inside one skill's alternation.
    parts = [rf"(?i:{re.escape(t)})" for t in sorted(set(ci), key=len, reverse=True)]
    parts += [re.escape(t) for t in cs]  # "=" aliases stay case-sensitive
    return re.compile(rf"(?<![\w])(?:{'|'.join(parts)})(?![\w])")


def parse_custom(text: str) -> list[tuple[str, list[str]]]:
    """'Name: alias1, alias2' per line -> [(name, [aliases])]."""
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, rest = line.partition(":")
        if name.strip():
            out.append((name.strip(), [a.strip() for a in rest.split(",") if a.strip()]))
    return out


@lru_cache(maxsize=8)
def library(custom_text: str = "") -> tuple[Skill, ...]:
    data = yaml.safe_load(LIBRARY_FILE.read_text(encoding="utf-8")) or {}
    skills: dict[str, Skill] = {}
    for category, entries in data.items():
        for name, aliases in (entries or {}).items():
            skills[name.lower()] = Skill(name, category, _compile(name, aliases or []))
    for name, aliases in parse_custom(custom_text):
        skills[name.lower()] = Skill(name, "custom", _compile(name, aliases))
    return tuple(skills.values())


def find(text: str, lib: tuple[Skill, ...]) -> dict[str, int]:
    """Skill name -> number of mentions."""
    found = {}
    if not text:
        return found
    for s in lib:
        n = len(s.pattern.findall(text))
        if n:
            found[s.name] = n
    return found


def by_name(lib: tuple[Skill, ...]) -> dict[str, Skill]:
    return {s.name: s for s in lib}
