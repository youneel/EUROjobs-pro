"""Adzuna jobs API. Requires ADZUNA_APP_ID + ADZUNA_APP_KEY.

Adzuna covers many countries and all sectors. Attribution is shown in the
footer. We request sponsorship-related keywords per country.
"""
from __future__ import annotations

import httpx

from app.config import settings
from app.data import currency_for
from app.sources.base import NormalizedListing, SourceError, iso_date, salary_from_fields
from app.utils import detect_country

API = "https://api.adzuna.com/v1/api/jobs/{country}/search/1"
DEFAULT_COUNTRIES = ["gb", "us", "ca", "au", "de", "fr", "nl", "sg", "ie", "nz"]


class AdzunaSource:
    name = "adzuna"

    @property
    def enabled(self) -> bool:
        return bool(settings.adzuna_app_id and settings.adzuna_app_key)

    async def fetch(self, client: httpx.AsyncClient) -> list[NormalizedListing]:
        if not self.enabled:
            return []
        results: list[NormalizedListing] = []
        for country in DEFAULT_COUNTRIES:
            try:
                response = await client.get(
                    API.format(country=country),
                    params={
                        "app_id": settings.adzuna_app_id,
                        "app_key": settings.adzuna_app_key,
                        "results_per_page": 50,
                        "what": "visa sponsorship",
                        "content-type": "application/json",
                    },
                )
                if response.status_code in {401, 403, 429}:
                    continue
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                if not results:
                    raise SourceError(f"Adzuna: {exc}") from exc
                continue
            results.extend(
                x for x in (self._normalize(item, country) for item in payload.get("results", [])) if x
            )
        return results

    async def search(self, client: httpx.AsyncClient, query: str, countries: list[str] | None = None) -> list[NormalizedListing]:
        if not self.enabled:
            return []
        results: list[NormalizedListing] = []
        for country in (countries or DEFAULT_COUNTRIES[:3]):
            try:
                response = await client.get(
                    API.format(country=country),
                    params={
                        "app_id": settings.adzuna_app_id,
                        "app_key": settings.adzuna_app_key,
                        "results_per_page": 20,
                        "what": query,
                        "content-type": "application/json",
                    },
                )
                if response.status_code >= 400:
                    continue
                payload = response.json()
            except (httpx.HTTPError, ValueError):
                continue
            results.extend(
                x for x in (self._normalize(item, country) for item in payload.get("results", [])) if x
            )
        return results

    def _normalize(self, item: dict, country_hint: str) -> NormalizedListing | None:
        title = item.get("title") or ""
        company = (item.get("company") or {}).get("display_name") or ""
        url = item.get("redirect_url") or ""
        if not title or not company or not url:
            return None
        location = (item.get("location") or {}).get("display_name") or ""
        code, country = detect_country(location)
        code = code or country_hint
        country = country or (code.upper() if code else None)
        contract_time = item.get("contract_time")
        contract_type = item.get("contract_type")
        employment = None
        if contract_time in {"full_time", "part_time"}:
            employment = contract_time
        elif contract_type == "contract":
            employment = "contract"
        low, high, currency = salary_from_fields(
            item.get("salary_min"), item.get("salary_max"), currency_for(code), country_code=code
        )
        return NormalizedListing(
            source_name="adzuna",
            source_job_id=str(item.get("id") or url),
            title=title,
            company=company,
            apply_url=url,
            description_html=item.get("description"),
            country=country or (code or "").upper() or None,
            country_code=code,
            city=location.split(",")[0].strip() if location else None,
            employment_type=employment,
            category=(item.get("category") or {}).get("label"),
            salary_min=low,
            salary_max=high,
            currency=currency,
            posted_at=iso_date(item.get("created")),
            extras={"location": location, "tags": (item.get("category") or {}).get("label")},
        )
