"""Reed.co.uk jobs API. Requires REED_API_KEY (HTTP Basic, key as username)."""
from __future__ import annotations

import base64

import httpx

from app.config import settings
from app.sources.base import NormalizedListing, SourceError, iso_date, salary_from_fields

API = "https://www.reed.co.uk/api/1.0/search"


class ReedSource:
    name = "reed"

    @property
    def enabled(self) -> bool:
        return bool(settings.reed_api_key)

    def _auth_header(self) -> dict[str, str]:
        token = base64.b64encode(f"{settings.reed_api_key}:".encode()).decode()
        return {"Authorization": f"Basic {token}"}

    async def fetch(self, client: httpx.AsyncClient) -> list[NormalizedListing]:
        if not self.enabled:
            return []
        results: list[NormalizedListing] = []
        for keyword in ("visa sponsorship", "work permit"):
            try:
                response = await client.get(
                    API,
                    params={"keywords": keyword, "resultsToTake": 100},
                    headers=self._auth_header(),
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                if results:
                    break
                raise SourceError(f"Reed: {exc}") from exc
            results.extend(
                x for x in (self._normalize(item) for item in payload.get("results", [])) if x
            )
        return results

    async def search(self, client: httpx.AsyncClient, query: str) -> list[NormalizedListing]:
        if not self.enabled:
            return []
        try:
            response = await client.get(
                API,
                params={"keywords": query, "resultsToTake": 25},
                headers=self._auth_header(),
            )
            if response.status_code >= 400:
                return []
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return []
        return [x for x in (self._normalize(item) for item in payload.get("results", [])) if x]

    def _normalize(self, item: dict) -> NormalizedListing | None:
        title = item.get("jobTitle") or ""
        company = item.get("employerName") or ""
        url = item.get("jobUrl") or ""
        if not title or not company or not url:
            return None
        location = item.get("locationName") or ""
        low, high, currency = salary_from_fields(
            item.get("minimumSalary"), item.get("maximumSalary"), item.get("currency") or "GBP"
        )
        contract = (item.get("contractType") or "").lower()
        employment = "full_time" if item.get("fullTime") else ("part_time" if item.get("partTime") else None)
        if contract == "contract":
            employment = "contract"
        return NormalizedListing(
            source_name="reed",
            source_job_id=str(item.get("jobId") or url),
            title=title,
            company=company,
            apply_url=url,
            description_html=item.get("jobDescription"),
            country="United Kingdom",
            country_code="gb",
            city=location,
            work_mode="remote" if "remote" in location.lower() else None,
            employment_type=employment,
            salary_min=low,
            salary_max=high,
            currency=currency,
            posted_at=iso_date(item.get("date")),
            extras={"location": location},
        )
