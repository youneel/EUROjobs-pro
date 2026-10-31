"""The Muse public jobs API.

The Muse can block datacentre traffic (HTTP 403). The adapter fails softly and
never breaks an ingestion run.
"""
from __future__ import annotations

import httpx

from app.sources.base import NormalizedListing, SourceError, iso_date
from app.utils import detect_country

API = "https://www.themuse.com/api/public/jobs"


class TheMuseSource:
    name = "themuse"

    @property
    def enabled(self) -> bool:
        return True

    @staticmethod
    def _normalize(item: dict) -> NormalizedListing | None:
        title = item.get("name") or ""
        company = (item.get("company") or {}).get("name") or ""
        url = ((item.get("refs") or {}).get("landing_page")) or ""
        if not title or not company or not url:
            return None
        locations = [str((loc or {}).get("name") or "") for loc in item.get("locations") or []]
        location = ", ".join(x for x in locations if x)
        code, country = detect_country(location)
        if any("remote" in x.lower() for x in locations):
            mode = "remote"
        elif any("hybrid" in x.lower() for x in locations):
            mode = "hybrid"
        else:
            mode = None
        levels = item.get("levels") or []
        categories = [str((c or {}).get("name") or "") for c in item.get("categories") or []]
        return NormalizedListing(
            source_name="themuse",
            source_job_id=str(item.get("id") or url),
            title=title,
            company=company,
            apply_url=url,
            description_html=item.get("contents"),
            company_logo_url=(item.get("company") or {}).get("logo") or None,
            country=country,
            country_code=code,
            work_mode=mode,
            seniority=(str((levels[0] or {}).get("name") or "").lower() if levels else None),
            posted_at=iso_date(item.get("publication_date")),
            extras={
                "tags": ", ".join(categories),
                "location": location,
                "remote": mode == "remote",
            },
        )

    async def fetch(self, client: httpx.AsyncClient, pages: int = 2) -> list[NormalizedListing]:
        results: list[NormalizedListing] = []
        for page in range(1, max(1, pages) + 1):
            try:
                response = await client.get(API, params={"page": page})
                if response.status_code in {401, 403, 429}:
                    break
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                if results:
                    break
                raise SourceError(f"The Muse: {exc}") from exc
            results.extend(
                x for x in (self._normalize(item) for item in payload.get("results", [])) if x
            )
            if page >= int(payload.get("page_count") or 1):
                break
        return results

    async def search(self, client: httpx.AsyncClient, query: str) -> list[NormalizedListing]:
        try:
            response = await client.get(API, params={"page": 1, "keywords": query})
            if response.status_code >= 400:
                return []
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return []
        return [x for x in (self._normalize(item) for item in payload.get("results", [])) if x]
