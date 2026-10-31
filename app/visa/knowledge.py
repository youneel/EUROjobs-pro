"""Verified visa knowledge base used by the assistant and the visa pages."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.yamlcompat import safe_load

from app.config import DATA_DIR

KNOWLEDGE_FILE = DATA_DIR / "visa_knowledge.yaml"


@dataclass
class VisaEntry:
    key: str
    country: str
    name: str
    volunteer: bool
    duration: str
    sponsorship: str
    official_url: str
    updated: str
    summary: dict[str, str]

    def localised(self, lang: str) -> str:
        return self.summary.get(lang) or self.summary.get("en") or ""

    def as_dict(self, lang: str) -> dict:
        return {
            "key": self.key,
            "country": self.country,
            "name": self.name,
            "volunteer": self.volunteer,
            "duration": self.duration,
            "sponsorship": self.sponsorship,
            "official_url": self.official_url,
            "updated": self.updated,
            "summary": self.localised(lang),
        }


@lru_cache
def load_knowledge() -> list[VisaEntry]:
    if not KNOWLEDGE_FILE.exists():
        return []
    payload = safe_load(KNOWLEDGE_FILE.read_text(encoding="utf-8")) or {}
    entries = []
    for item in payload.get("entries", []):
        summary = item.get("summary") or {}
        entries.append(
            VisaEntry(
                key=str(item.get("key") or ""),
                country=str(item.get("country") or "worldwide").lower(),
                name=str(item.get("name") or ""),
                volunteer=bool(item.get("volunteer")),
                duration=str(item.get("duration") or ""),
                sponsorship=str(item.get("sponsorship") or ""),
                official_url=str(item.get("official_url") or ""),
                updated=str(item.get("updated") or ""),
                summary={str(k): str(v) for k, v in summary.items()},
            )
        )
    return entries


def lookup(country: str | None = None, volunteer: bool | None = None, query: str = "") -> list[VisaEntry]:
    from app.utils import fold_text

    entries = load_knowledge()
    code = (country or "").lower()
    if code in {"gb", "uk"}:
        code = "gb"
    q = fold_text(query)
    out = []
    for entry in entries:
        if code and entry.country not in {code, "worldwide", "eu"}:
            continue
        if volunteer is True and not entry.volunteer:
            continue
        if volunteer is False and entry.volunteer:
            continue
        if q and q not in fold_text(f"{entry.name} {entry.sponsorship} {entry.localised('en')}"):
            continue
        out.append(entry)
    if not out and code:
        out = [e for e in entries if e.country in {code, "worldwide"}]
    return out[:12]
