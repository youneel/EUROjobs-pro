"""RemoteOK public JSON feed (free; attribution + link-back required)."""
from __future__ import annotations

import httpx

from app.sources.base import NormalizedListing, SourceError, iso_date, salary_from_fields
from app.utils import detect_country

API = "https://remoteok.com/api"


class RemoteOKSource:
    name = "remoteok"

    @property
    def enabled(self) -> bool:
        return True

    async def fetch(self, client: httpx.AsyncClient) -> list[NormalizedListing]:
        try:
            response = await client.get(API)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SourceError(f"RemoteOK: {exc}") from exc
        # The first element is a legal notice.
        items = [x for x in payload if isinstance(x, dict) and x.get("id")]
        return [x for x in (self._normalize(item) for item in items) if x]

    def _normalize(self, item: dict) -> NormalizedListing | None:
        title = item.get("position") or ""
        company = item.get("company") or ""
        url = item.get("apply_url") or item.get("url") or ""
        if not title or not company or not url:
            return None
        location = item.get("location") or ""
        code, country = detect_country(location)
        low, high, currency = salary_from_fields(item.get("salary_min"), item.get("salary_max"), None)
        return NormalizedListing(
            source_name=self.name,
            source_job_id=str(item.get("id") or url),
            title=title,
            company=company,
            apply_url=url,
            description_html=item.get("description"),
            company_logo_url=item.get("company_logo") or item.get("logo") or None,
            country=country,
            country_code=code,
            work_mode="remote",
            salary_min=low,
            salary_max=high,
            currency=currency,
            posted_at=iso_date(item.get("date") or item.get("epoch")),
            extras={
                "tags": ", ".join(item.get("tags") or []),
                "remote": True,
                "location": location,
                "original_url": item.get("url"),
            },
        )

    async def search(self, client: httpx.AsyncClient, query: str) -> list[NormalizedListing]:
        return []
