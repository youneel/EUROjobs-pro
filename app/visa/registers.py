"""Official sponsor-register loading and employer matching.

Registers are plain CSV/JSON files in ``data/registers``. Each row needs:
    company, country, route, source
``country`` is an ISO2 code. A UK licence therefore never matches a US job.
Use ``scripts/refresh_registers.py`` to download the public datasets, or drop
your own export in the folder. Files are refreshed by an admin task.
"""
from __future__ import annotations

import csv
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from rapidfuzz import fuzz

from app.config import DATA_DIR
from app.utils import normalize_company

log = logging.getLogger(__name__)
REGISTER_DIR = DATA_DIR / "registers"

# Below this fuzzy score we refuse the match: a false "verified sponsor" badge
# is worse than a missed one.
MATCH_THRESHOLD = 93


@dataclass
class RegisterEntry:
    company: str
    normalized: str
    country: str
    route: str
    source: str


@dataclass
class RegisterStore:
    entries: list[RegisterEntry] = field(default_factory=list)
    by_country: dict[str, list[RegisterEntry]] = field(default_factory=dict)
    loaded_at: datetime | None = None
    files: list[str] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def load(self) -> None:
        with self._lock:
            entries: list[RegisterEntry] = []
            files: list[str] = []
            if REGISTER_DIR.exists():
                for path in sorted(REGISTER_DIR.iterdir()):
                    if path.suffix.lower() not in {".csv", ".json"}:
                        continue
                    try:
                        rows = self._read(path)
                    except Exception as exc:  # pragma: no cover - bad file
                        log.warning("Register %s could not be read: %s", path.name, exc)
                        continue
                    for row in rows:
                        company = str(row.get("company") or row.get("employer") or "").strip()
                        country = str(row.get("country") or "").strip().lower()
                        if not company or len(country) != 2:
                            continue
                        entries.append(
                            RegisterEntry(
                                company=company,
                                normalized=normalize_company(company),
                                country=country,
                                route=str(row.get("route") or "all routes").strip(),
                                source=str(row.get("source") or path.name).strip(),
                            )
                        )
                    files.append(path.name)
            by_country: dict[str, list[RegisterEntry]] = {}
            for entry in entries:
                by_country.setdefault(entry.country, []).append(entry)
            self.entries = entries
            self.by_country = by_country
            self.files = files
            self.loaded_at = datetime.now(timezone.utc)
            log.info("Loaded %s sponsor register entries from %s files", len(entries), len(files))

    @staticmethod
    def _read(path: Path) -> list[dict]:
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            return payload if isinstance(payload, list) else payload.get("entries", [])
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            sample = fh.read(4096)
            fh.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            return list(csv.DictReader(fh, dialect=dialect))

    def match(self, company: str, country_code: str | None) -> RegisterEntry | None:
        if not company or not country_code:
            return None
        candidates = self.by_country.get(country_code.lower(), [])
        if not candidates:
            return None
        target = normalize_company(company)
        if not target or len(target) < 3:
            return None
        best: RegisterEntry | None = None
        best_score = 0.0
        for entry in candidates:
            name = entry.normalized
            if not name:
                continue
            if target == name:
                return entry
            # Containment only counts when the shorter name is substantial;
            # "Care" must not match "Care UK plc".
            shorter, longer = sorted((target, name), key=len)
            if len(shorter) >= 6 and shorter in longer:
                score = 96.0
            else:
                score = float(fuzz.token_set_ratio(target, name))
            if score > best_score:
                best_score, best = score, entry
            if score == 100:
                break
        return best if best_score >= MATCH_THRESHOLD else None

    def coverage(self) -> dict[str, int]:
        return {country: len(items) for country, items in sorted(self.by_country.items())}


_store = RegisterStore()


def get_registers() -> RegisterStore:
    if _store.loaded_at is None:
        _store.load()
    return _store


def reload_registers() -> RegisterStore:
    _store.load()
    return _store
