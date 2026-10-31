"""Volunteer programme registry loaded from ``data/volunteer_programs.yaml``.

Only entries with ``verified: true`` are shown or used as Level 1 evidence.
An entry is verified only when its official page documents visa support or an
invitation letter. The loader is intentionally strict.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from app.yamlcompat import safe_load

from app.config import DATA_DIR
from app.utils import fold_text

log = logging.getLogger(__name__)
PROGRAMS_FILE = DATA_DIR / "volunteer_programs.yaml"


@dataclass
class VolunteerProgram:
    name: str
    country: str | None
    org_type: str
    official_url: str
    application_url: str | None
    visa_support: str
    evidence_url: str
    verified_on: str
    verified: bool
    fee_required: bool = False
    fee_amount: float | None = None
    fee_currency: str | None = None
    notes: str | None = None
    aliases: list[str] | None = None

    @property
    def evidence(self) -> str:
        return f"{self.name}: {self.visa_support} ({self.evidence_url})"


@lru_cache
def load_programs() -> list[VolunteerProgram]:
    if not PROGRAMS_FILE.exists():
        return []
    try:
        payload = safe_load(PROGRAMS_FILE.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # pragma: no cover - config error
        log.error("volunteer_programs.yaml is invalid: %s", exc)
        return []
    items = payload.get("programs", payload if isinstance(payload, list) else [])
    programmes: list[VolunteerProgram] = []
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        verified = bool(item.get("verified"))
        evidence_url = str(item.get("evidence_url") or "").strip()
        visa_support = str(item.get("visa_support") or "").strip()
        # A verified entry must carry auditable evidence.
        if verified and (not evidence_url.startswith("http") or not visa_support):
            log.warning("Dropping %s: verified without evidence URL/visa support", name)
            verified = False
        programmes.append(
            VolunteerProgram(
                name=name,
                country=(str(item.get("country")).lower() if item.get("country") else None),
                org_type=str(item.get("org_type") or "ngo"),
                official_url=str(item.get("official_url") or "").strip(),
                application_url=str(item.get("application_url") or "").strip() or None,
                visa_support=visa_support,
                evidence_url=evidence_url,
                verified_on=str(item.get("verified_on") or ""),
                verified=verified,
                fee_required=bool(item.get("fee_required")),
                fee_amount=item.get("fee_amount"),
                fee_currency=item.get("fee_currency"),
                notes=item.get("notes"),
                aliases=[str(a) for a in (item.get("aliases") or [])],
            )
        )
    return programmes


def match_program(company: str, country_code: str | None = None) -> VolunteerProgram | None:
    target = fold_text(company)
    if not target:
        return None
    for programme in load_programs():
        if not programme.verified:
            continue
        names = [programme.name, *(programme.aliases or [])]
        for name in names:
            folded = fold_text(name)
            if folded and (folded == target or (len(folded) >= 8 and folded in target)):
                if country_code and programme.country and programme.country != country_code.lower():
                    continue
                return programme
    return None


def verified_programs() -> list[VolunteerProgram]:
    return [p for p in load_programs() if p.verified]
