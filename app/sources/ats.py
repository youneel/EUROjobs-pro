"""Public ATS board adapters: Greenhouse, Lever, Ashby, Workable, SmartRecruiters.

No scraping: these are the same public JSON endpoints each employer publishes
for its own careers page. Boards are config-driven in ``data/companies.yaml``
and validated at ingest; a failing board is skipped, never fatal.
"""
from __future__ import annotations

import html
import logging
import re
from pathlib import Path

import httpx
from app.yamlcompat import safe_load

from app.config import DATA_DIR
from app.sources.base import NormalizedListing, iso_date, salary_from_fields
from app.utils import detect_country, domain_from_url, fold_text

log = logging.getLogger(__name__)
COMPANIES_FILE = DATA_DIR / "companies.yaml"
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")


def load_companies() -> list[dict]:
    if not COMPANIES_FILE.exists():
        return []
    try:
        payload = safe_load(COMPANIES_FILE.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - config error
        log.error("companies.yaml is invalid: %s", exc)
        return []
    rows = payload.get("companies", payload if isinstance(payload, list) else [])
    out: list[dict] = []
    for row in rows:
        slug = str(row.get("slug") or "").strip()
        ats = str(row.get("ats") or "").strip().lower()
        if ats not in {"greenhouse", "lever", "ashby", "workable", "smartrecruiters"}:
            continue
        if not SLUG_RE.match(slug):
            continue
        if row.get("enabled", True) is False:
            continue
        out.append({**row, "slug": slug, "ats": ats})
    return out


GREENHOUSE = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
LEVER = "https://api.lever.co/v0/postings/{slug}?mode=json"
ASHBY = "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
WORKABLE = "https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"
SMARTRECRUITERS = "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100"


class AtsSource:
    """One ATS source instance per configured employer board."""

    def __init__(self, config: dict):
        self.config = config
        self.ats = config["ats"]
        self.slug = config["slug"]
        self.name = f"ats:{self.ats}:{self.slug}"
        self._board_ok: bool | None = None

    @property
    def enabled(self) -> bool:
        return True

    async def fetch(self, client: httpx.AsyncClient) -> list[NormalizedListing]:
        url = {
            "greenhouse": GREENHOUSE, "lever": LEVER, "ashby": ASHBY,
            "workable": WORKABLE, "smartrecruiters": SMARTRECRUITERS,
        }[self.ats].format(slug=self.slug)
        try:
            response = await client.get(url)
            if response.status_code == 404:
                self._board_ok = False
                return []
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.debug("Board %s failed: %s", self.name, exc)
            return []
        self._board_ok = True
        try:
            return [x for x in (self._normalize(item) for item in self._items(payload)) if x]
        except Exception as exc:  # pragma: no cover - unusual board shape
            log.warning("Board %s returned an unexpected shape: %s", self.name, exc)
            return []

    async def search(self, client: httpx.AsyncClient, query: str) -> list[NormalizedListing]:
        return []

    def _items(self, payload) -> list[dict]:
        if self.ats in {"greenhouse"}:
            return payload.get("jobs", [])
        if self.ats == "lever":
            return payload if isinstance(payload, list) else []
        if self.ats in {"ashby"}:
            return payload.get("jobs", [])
        if self.ats == "workable":
            return payload.get("jobs", [])
        if self.ats == "smartrecruiters":
            return payload.get("content", [])
        return []

    def _normalize(self, item: dict) -> NormalizedListing | None:
        if self.ats == "greenhouse":
            title = item.get("title") or ""
            url = item.get("absolute_url") or ""
            location = (item.get("location") or {}).get("name") or ""
            description = html.unescape(item.get("content") or "")
            posted = item.get("updated_at") or item.get("first_published")
            employment = None
            seniority = None
        elif self.ats == "lever":
            title = item.get("text") or ""
            url = item.get("applyUrl") or item.get("hostedUrl") or ""
            categories = item.get("categories") or {}
            location = categories.get("location") or ""
            description = (item.get("description") or "") + _lever_lists(item.get("lists") or [])
            posted = item.get("createdAt")
            employment = _employment_from(categories.get("commitment"))
            seniority = None
        elif self.ats == "ashby":
            title = item.get("title") or ""
            url = item.get("applyUrl") or item.get("jobUrl") or ""
            location = item.get("location") or ""
            description = item.get("descriptionHtml") or item.get("descriptionPlain") or ""
            posted = item.get("publishedAt")
            employment = _employment_from(item.get("employmentType"))
            seniority = None
        elif self.ats == "workable":
            title = item.get("title") or ""
            url = item.get("application_url") or item.get("url") or ""
            loc = item.get("location") or {}
            location = ", ".join(x for x in (loc.get("city"), loc.get("country")) if x)
            description = " ".join(
                str(item.get(k) or "") for k in ("description", "requirements", "benefits")
            )
            posted = item.get("created_at")
            employment = _employment_from(item.get("type"))
            seniority = None
        else:  # smartrecruiters
            title = item.get("name") or ""
            url = item.get("ref") or ""
            loc = item.get("location") or {}
            location = ", ".join(x for x in (loc.get("city"), loc.get("country")) if x)
            description = ""
            posted = item.get("releasedDate")
            employment = _employment_from((item.get("typeOfEmployment") or {}).get("label"))
            seniority = None

        company = self.config.get("name") or self.slug
        if not title or not url:
            return None
        code, country = detect_country(location, self.config.get("country"))
        if not code and self.config.get("country"):
            code = str(self.config["country"]).lower()
        is_remote = "remote" in location.lower() or bool(item.get("isRemote")) or bool(
            (item.get("location") or {}).get("remote") if isinstance(item.get("location"), dict) else False
        )
        low, high, currency = salary_from_fields(None, None, None)
        if self.ats == "ashby":
            comp = (item.get("compensation") or {}).get("compensationTierSummary")
            if comp:
                low, high, currency = salary_from_fields(None, None, None, str(comp), code)
        return NormalizedListing(
            source_name=self.name,
            source_job_id=str(item.get("id") or url),
            title=title,
            company=company,
            apply_url=url,
            description_html=description,
            company_url=self.config.get("website") or (f"https://{self.config['domain']}" if self.config.get("domain") else None),
            company_domain=self.config.get("domain") or domain_from_url(self.config.get("website")),
            country=country or (code.upper() if code else None),
            country_code=code,
            city=location.split(",")[0].strip() if location else None,
            work_mode="remote" if is_remote else None,
            employment_type=employment,
            seniority=seniority,
            salary_min=low,
            salary_max=high,
            currency=currency,
            posted_at=iso_date(posted),
            extras={
                "location": location,
                "organization_type": self.config.get("type", "company"),
                "board": self.name,
            },
        )


def _lever_lists(lists: list[dict]) -> str:
    parts = []
    for section in lists:
        parts.append(f"<h3>{html.escape(str(section.get('text') or ''))}</h3>")
        parts.append(str(section.get("content") or ""))
    return "".join(parts)


def _employment_from(value) -> str | None:
    if not value:
        return None
    text = fold_text(str(value))
    if "intern" in text:
        return "internship"
    if "apprentice" in text:
        return "apprenticeship"
    if "part" in text:
        return "part_time"
    if "contract" in text or "temporary" in text:
        return "contract"
    if "season" in text:
        return "temporary"
    if "full" in text or "permanent" in text:
        return "full_time"
    return None


def ats_sources() -> list[AtsSource]:
    return [AtsSource(cfg) for cfg in load_companies()]
