"""Official sponsor-register loading and employer matching.

Registers are plain CSV/JSON files in ``data/registers``. Each row needs:
    company, country, route, source
``country`` is an ISO2 code. A UK licence therefore never matches a US job.
Use ``scripts/refresh_registers.py`` to download the public datasets, or drop
your own export in the folder. Files are refreshed by an admin task.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from rapidfuzz import fuzz

from app.config import DATA_DIR
from app.utils import normalize_company

log = logging.getLogger(__name__)
REGISTER_DIR = DATA_DIR / "registers"
UK_REGISTER_PAGE = "https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers"
UK_REGISTER_SOURCE = "UK Home Office Register of Worker and Temporary Worker licensed sponsors"
UK_ALLOWED_HOSTS = {"www.gov.uk", "assets.publishing.service.gov.uk"}


class _DownloadLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href", "")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            self.links.append((" ".join(self._text).strip(), self._href))
            self._href = ""
            self._text = []


def refresh_uk_register_if_stale(max_age_days: int = 7) -> dict:
    """Refresh the UK Home Office CSV, preserving the last good file on errors."""
    path = REGISTER_DIR / "uk_home_office.json"
    if path.exists():
        age_days = (datetime.now(timezone.utc).timestamp() - path.stat().st_mtime) / 86400
        if age_days < max_age_days:
            return {"updated": False, "reason": "fresh", "entries": 0}

    REGISTER_DIR.mkdir(parents=True, exist_ok=True)
    timeout = httpx.Timeout(30.0, connect=10.0)
    with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": "WorkAtlasPro/2.0 (official register refresh)"}) as client:
        page = client.get(UK_REGISTER_PAGE)
        page.raise_for_status()
        links = _DownloadLinks()
        links.feed(page.text)
        href = next(
            (
                value for label, value in links.links
                if "Register of Worker and Temporary Worker licensed sponsors" in label
                and ".csv" in value.lower()
            ),
            None,
        )
        if not href:
            raise RuntimeError("The GOV.UK sponsor register CSV link was not found")
        download_url = urljoin(UK_REGISTER_PAGE, href)
        if urlparse(download_url).hostname not in UK_ALLOWED_HOSTS:
            raise RuntimeError("The sponsor register download link points to an unapproved host")
        download = client.get(download_url)
        download.raise_for_status()

    reader = csv.DictReader(io.StringIO(download.content.decode("utf-8-sig")))
    if not reader.fieldnames:
        raise RuntimeError("The downloaded sponsor register has no CSV header")
    fields = {re.sub(r"[^a-z]", "", name.lower()): name for name in reader.fieldnames}
    company_key = next((fields[k] for k in ("organisationname", "organizationname") if k in fields), None)
    route_key = fields.get("route")
    if not company_key or not route_key:
        raise RuntimeError(f"Unexpected UK register columns: {reader.fieldnames!r}")

    entries = [
        {
            "company": row.get(company_key, "").strip(),
            "country": "gb",
            "route": row.get(route_key, "all routes").strip() or "all routes",
            "source": UK_REGISTER_SOURCE,
        }
        for row in reader
        if row.get(company_key, "").strip()
    ]
    if not entries:
        raise RuntimeError("The downloaded UK sponsor register contains no organisations")
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    reload_registers()
    log.info("Updated the UK Home Office sponsor register with %s organisations", len(entries))
    return {"updated": True, "reason": "downloaded", "entries": len(entries)}

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
