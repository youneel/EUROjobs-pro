"""Himalayas public jobs API (free; server-side only)."""
from __future__ import annotations

import httpx

from app.sources.base import NormalizedListing, SourceError, iso_date, salary_from_fields
from app.utils import detect_country

API = "https://himalayas.app/jobs/api"


class HimalayasSource:
    name = "himalayas"

    @property
    def enabled(self) -> bool:
        return True

    async def fetch(self, client: httpx.AsyncClient, limit: int = 100) -> list[NormalizedListing]:
        try:
            response = await client.get(API, params={"limit": limit})
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SourceError(f"Himalayas: {exc}") from exc
        return [x for x in (self._normalize(item) for item in payload.get("jobs", [])) if x]

    def _normalize(self, item: dict) -> NormalizedListing | None:
        title = item.get("title") or ""
        company = item.get("companyName") or ""
        url = item.get("applicationLink") or item.get("guid") or ""
        if not title or not company or not url:
            return None
        restrictions = item.get("locationRestrictions") or []
        location = ", ".join(str(x) for x in restrictions[:3])
        code, country = detect_country(location)
        if len(restrictions) > 3 or not restrictions:
            code, country = None, None
        salary_period = (item.get("salaryPeriod") or "").lower()
        low, high, currency = salary_from_fields(
            item.get("minSalary"), item.get("maxSalary"), item.get("currency"), country_code=code
        )
        if low and salary_period in {"hourly", "daily"}:
            low, high = low * 2000, (high * 2000 if high else None)
        seniority = item.get("seniority") or []
        return NormalizedListing(
            source_name=self.name,
            source_job_id=str(item.get("guid") or url),
            title=title,
            company=company,
            apply_url=url,
            description_html=item.get("description") or item.get("excerpt"),
            company_logo_url=item.get("companyLogo") or None,
            country=country,
            country_code=code,
            work_mode="remote",
            employment_type=(str(item.get("employmentType") or "").lower().replace(" ", "_") or None),
            seniority=(str(seniority[0]).lower() if seniority else None),
            salary_min=low,
            salary_max=high,
            currency=currency,
            posted_at=iso_date(item.get("pubDate")),
            extras={
                "tags": ", ".join(item.get("categories") or []),
                "remote": True,
                "location": location,
                "company_slug": item.get("companySlug"),
            },
        )

    async def search(self, client: httpx.AsyncClient, query: str) -> list[NormalizedListing]:
        try:
            response = await client.get(API, params={"limit": 20, "search": query})
            if response.status_code >= 400:
                return []
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return []
        return [x for x in (self._normalize(item) for item in payload.get("jobs", [])) if x]
