"""Remotive remote-jobs API (free, no key; attribution required)."""
from __future__ import annotations

import httpx

from app.sources.base import NormalizedListing, SourceError, iso_date
from app.utils import detect_country

API = "https://remotive.com/api/remote-jobs"


class RemotiveSource:
    name = "remotive"

    @property
    def enabled(self) -> bool:
        return True

    @staticmethod
    def _normalize(item: dict) -> NormalizedListing | None:
        title = item.get("title") or ""
        company = item.get("company_name") or ""
        url = item.get("url") or ""
        if not title or not company or not url:
            return None
        location = item.get("candidate_required_location") or ""
        code, country = detect_country(location)
        if location.lower() in {"worldwide", "anywhere", "remote"}:
            code, country = None, None
        job_type = (item.get("job_type") or "full_time").replace("-", "_")
        return NormalizedListing(
            source_name="remotive",
            source_job_id=str(item.get("id") or url),
            title=title,
            company=company,
            apply_url=url,
            description_html=item.get("description"),
            company_logo_url=item.get("company_logo") or None,
            country=country,
            country_code=code,
            city=None,
            work_mode="remote",
            employment_type=job_type,
            salary_min=None,
            salary_max=None,
            currency=None,
            posted_at=iso_date(item.get("publication_date")),
            extras={
                "tags": ", ".join(item.get("tags") or []),
                "remote": True,
                "location": location,
                "category": item.get("category"),
                "salary": item.get("salary"),
            },
        )

    async def fetch(self, client: httpx.AsyncClient, limit: int = 100) -> list[NormalizedListing]:
        try:
            response = await client.get(API, params={"limit": limit})
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SourceError(f"Remotive: {exc}") from exc
        return [x for x in (self._normalize(item) for item in payload.get("jobs", [])) if x]

    async def search(self, client: httpx.AsyncClient, query: str) -> list[NormalizedListing]:
        try:
            response = await client.get(API, params={"search": query, "limit": 20})
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return []
        return [x for x in (self._normalize(item) for item in payload.get("jobs", [])) if x]
