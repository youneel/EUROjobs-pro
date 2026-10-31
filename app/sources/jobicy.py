"""Jobicy remote-jobs API (free, no key)."""
from __future__ import annotations

import httpx

from app.sources.base import NormalizedListing, SourceError, iso_date, salary_from_fields
from app.utils import detect_country

API = "https://jobicy.com/api/v2/remote-jobs"


class JobicySource:
    name = "jobicy"

    @property
    def enabled(self) -> bool:
        return True

    async def fetch(self, client: httpx.AsyncClient, count: int = 50) -> list[NormalizedListing]:
        try:
            response = await client.get(API, params={"count": count})
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SourceError(f"Jobicy: {exc}") from exc
        return [x for x in (self._normalize(item) for item in payload.get("jobs", [])) if x]

    async def search(self, client: httpx.AsyncClient, query: str) -> list[NormalizedListing]:
        # Jobicy exposes industry/geo filters, not free-text search. The
        # database already holds its ingest; live search adds nothing here.
        return []

    def _normalize(self, item: dict) -> NormalizedListing | None:
        title = item.get("jobTitle") or ""
        company = item.get("companyName") or ""
        url = item.get("url") or ""
        if not title or not company or not url:
            return None
        geo = item.get("jobGeo") or ""
        code, country = detect_country(geo)
        if geo.lower() in {"anywhere", "worldwide", "remote"}:
            code, country = None, None
        job_type = item.get("jobType")
        if isinstance(job_type, list):
            job_type = job_type[0] if job_type else None
        low, high, currency = salary_from_fields(
            item.get("annualSalaryMin"), item.get("annualSalaryMax"),
            item.get("salaryCurrency"), country_code=code,
        )
        return NormalizedListing(
            source_name=self.name,
            source_job_id=str(item.get("id") or url),
            title=title,
            company=company,
            apply_url=url,
            description_html=item.get("jobDescription") or item.get("jobExcerpt"),
            company_logo_url=item.get("companyLogo") or None,
            country=country,
            country_code=code,
            work_mode="remote",
            employment_type=(str(job_type).lower().replace("-", "_").replace(" ", "_") if job_type else None),
            seniority=(str(item.get("jobLevel")).lower() if item.get("jobLevel") else None),
            salary_min=low,
            salary_max=high,
            currency=currency,
            posted_at=iso_date(item.get("pubDate")),
            extras={
                "tags": ", ".join(item.get("jobIndustry") or []),
                "remote": True,
                "location": geo,
            },
        )
