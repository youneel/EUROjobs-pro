"""Jooble API. Requires JOOBLE_API_KEY."""
from __future__ import annotations

import httpx

from app.config import settings
from app.sources.base import NormalizedListing, SourceError, iso_date, salary_from_fields
from app.utils import detect_country, parse_salary

API = "https://jooble.org/api/{key}"


class JoobleSource:
    name = "jooble"

    @property
    def enabled(self) -> bool:
        return bool(settings.jooble_api_key)

    async def fetch(self, client: httpx.AsyncClient) -> list[NormalizedListing]:
        if not self.enabled:
            return []
        results: list[NormalizedListing] = []
        for keyword in ("visa sponsorship", "work permit"):
            try:
                response = await client.post(
                    API.format(key=settings.jooble_api_key),
                    json={"keywords": keyword, "location": ""},
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                if results:
                    break
                raise SourceError(f"Jooble: {exc}") from exc
            results.extend(
                x for x in (self._normalize(item) for item in payload.get("jobs", [])) if x
            )
        return results

    async def search(self, client: httpx.AsyncClient, query: str) -> list[NormalizedListing]:
        if not self.enabled:
            return []
        try:
            response = await client.post(
                API.format(key=settings.jooble_api_key),
                json={"keywords": query, "location": ""},
            )
            if response.status_code >= 400:
                return []
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return []
        return [x for x in (self._normalize(item) for item in payload.get("jobs", [])) if x]

    def _normalize(self, item: dict) -> NormalizedListing | None:
        title = item.get("title") or ""
        company = item.get("company") or ""
        url = item.get("link") or ""
        if not title or not company or not url:
            return None
        location = item.get("location") or ""
        code, country = detect_country(location)
        salary_text = item.get("salary") or ""
        low, high, currency = salary_from_fields(None, None, None, salary_text, code)
        return NormalizedListing(
            source_name="jooble",
            source_job_id=str(item.get("id") or url),
            title=title,
            company=company,
            apply_url=url,
            description_text=item.get("snippet") or "",
            country=country,
            country_code=code,
            city=location,
            employment_type=(item.get("type") or "").lower().replace("-", "_") or None,
            salary_min=low,
            salary_max=high,
            currency=currency,
            posted_at=iso_date(item.get("updated")),
            extras={"location": location, "source_label": item.get("source")},
        )
