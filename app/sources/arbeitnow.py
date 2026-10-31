"""Arbeitnow public job-board API (free, Europe/Germany focus).

Docs: https://www.arbeitnow.com/api/job-board-api
The feed exposes an explicit ``visa_sponsorship`` boolean, which is used as an
explicit source flag (Tier 2 evidence) before phrase rules run.
"""
from __future__ import annotations

import httpx

from app.sources.base import NormalizedListing, SourceError, iso_date, salary_from_fields
from app.utils import detect_country

API = "https://www.arbeitnow.com/api/job-board-api"


class ArbeitnowSource:
    name = "arbeitnow"

    @property
    def enabled(self) -> bool:
        return True

    async def fetch(self, client: httpx.AsyncClient, pages: int = 4) -> list[NormalizedListing]:
        results: list[NormalizedListing] = []
        url = API
        for _ in range(max(1, pages)):
            try:
                response = await client.get(url)
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                if results:
                    break
                raise SourceError(f"Arbeitnow: {exc}") from exc
            for item in payload.get("data", []):
                listing = self._normalize(item)
                if listing:
                    results.append(listing)
            next_url = (payload.get("links") or {}).get("next")
            if not next_url:
                break
            url = next_url
        return results

    def _normalize(self, item: dict) -> NormalizedListing | None:
        title = item.get("title") or ""
        company = item.get("company_name") or ""
        apply_url = item.get("url") or ""
        if not title or not company or not apply_url:
            return None
        location = item.get("location") or ""
        code, country = detect_country(location)
        job_types = item.get("job_types") or []
        return NormalizedListing(
            source_name=self.name,
            source_job_id=str(item.get("slug") or item.get("url") or ""),
            title=title,
            company=company,
            apply_url=apply_url,
            description_html=item.get("description"),
            country=country,
            country_code=code,
            city=location.split(",")[0].strip() if location else None,
            work_mode="remote" if item.get("remote") else "onsite",
            employment_type=(job_types[0].lower().replace("-", "_") if job_types else None),
            language="en",
            source_flag=bool(item.get("visa_sponsorship")),
            posted_at=iso_date(item.get("created_at")),
            extras={"tags": ", ".join(item.get("tags") or []), "remote": bool(item.get("remote"))},
        )

    async def search(self, client: httpx.AsyncClient, query: str) -> list[NormalizedListing]:
        # The API has no keyword parameter; the live path is handled by the
        # database plus keyword-capable sources. Return nothing rather than
        # downloading the whole feed for every search.
        return []
