"""ReliefWeb API v2 (humanitarian jobs and volunteer placements).

Requires an approved RELIEFWEB_APPNAME. Without one the API returns 403 and the
adapter is skipped; the rest of the site keeps working.
"""
from __future__ import annotations

import httpx

from app.config import settings
from app.sources.base import NormalizedListing, SourceError, iso_date
from app.utils import detect_country

API = "https://api.reliefweb.int/v2/jobs"


class ReliefWebSource:
    name = "reliefweb"

    @property
    def enabled(self) -> bool:
        return bool(settings.reliefweb_appname)

    async def fetch(self, client: httpx.AsyncClient) -> list[NormalizedListing]:
        if not self.enabled:
            return []
        params: list[tuple[str, str]] = [
            ("appname", settings.reliefweb_appname),
            ("profile", "list"),
            ("limit", "100"),
            ("query[value]", "volunteer"),
            ("query[operator]", "AND"),
        ]
        for country in settings.reliefweb_country_list:
            params.append(("filter[field]", "country.iso3"))
            params.append(("filter[value]", country))
        try:
            response = await client.get(API, params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SourceError(f"ReliefWeb: {exc}") from exc
        return [x for x in (self._normalize(item) for item in payload.get("data", [])) if x]

    async def search(self, client: httpx.AsyncClient, query: str) -> list[NormalizedListing]:
        if not self.enabled:
            return []
        try:
            response = await client.get(
                API,
                params=[
                    ("appname", settings.reliefweb_appname),
                    ("limit", "20"),
                    ("query[value]", query),
                ],
            )
            if response.status_code >= 400:
                return []
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return []
        return [x for x in (self._normalize(item) for item in payload.get("data", [])) if x]

    def _normalize(self, entry: dict) -> NormalizedListing | None:
        fields = entry.get("fields") or {}
        title = fields.get("title") or ""
        sources = fields.get("source") or []
        company = (sources[0] or {}).get("name") if sources else ""
        url = fields.get("url") or ""
        if not title or not company or not url:
            return None
        countries = fields.get("country") or []
        location = (countries[0] or {}).get("name") if countries else ""
        code, country = detect_country(location)
        body = fields.get("body") or ""
        from app.visa.classifier import VOLUNTEER_HINTS

        is_volunteer = bool(VOLUNTEER_HINTS.search(title) or VOLUNTEER_HINTS.search(body[:4000]))
        return NormalizedListing(
            source_name="reliefweb",
            source_job_id=str(entry.get("id") or url),
            title=title,
            company=company,
            apply_url=url,
            description_html=body,
            country=country,
            country_code=code,
            listing_type="volunteer" if is_volunteer else "job",
            work_mode="remote" if "remote" in (location or "").lower() else None,
            posted_at=iso_date(fields.get("date", {}).get("created")),
            extras={"location": location, "organization_type": "ngo"},
        )
