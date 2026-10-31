"""Normalized listing schema shared by every source adapter."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import httpx

from app.utils import (
    detect_category,
    detect_country,
    detect_employment_type,
    detect_language,
    detect_seniority,
    detect_work_mode,
    domain_from_url,
    excerpt,
    fold_text,
    html_to_text,
    parse_date,
    parse_salary,
    sanitize_html,
    strip_tracking,
)

# Domains that are aggregators/ATS: never treated as the employer's own domain.
AGGREGATOR_DOMAINS = {
    "arbeitnow.com", "jobicy.com", "remotive.com", "remoteok.com", "himalayas.app",
    "themuse.com", "adzuna.com", "adzuna.co.uk", "jooble.org", "reed.co.uk",
    "reliefweb.int", "greenhouse.io", "lever.co", "ashbyhq.com", "workable.com",
    "smartrecruiters.com", "linkedin.com", "indeed.com", "glassdoor.com",
    "jobs.lever.co", "boards.greenhouse.io", "apply.workable.com",
}

USER_AGENT = "EuroJobsPro/2.0 (+https://example.invalid/about; job aggregation; contact via site)"


@dataclass
class VolunteerFields:
    duration: str | None = None
    start_date: date | None = None
    application_deadline: date | None = None
    hours_per_week: str | None = None
    cause_area: str | None = None
    org_type: str | None = None
    skills_required: str | None = None
    languages_required: str | None = None
    min_age: int | None = None
    remote_volunteering: bool = False
    accommodation_provided: bool | None = None
    meals_provided: bool | None = None
    stipend: float | None = None
    stipend_currency: str | None = None
    travel_covered: bool | None = None
    insurance_provided: bool | None = None
    fee_required: bool = False
    fee_amount: float | None = None
    fee_currency: str | None = None
    visa_support_type: str | None = None
    programme_name: str | None = None
    scam_flags: list[str] = field(default_factory=list)


@dataclass
class NormalizedListing:
    source_name: str
    source_job_id: str
    title: str
    company: str
    apply_url: str
    listing_type: str = "job"
    description_html: str | None = None
    description_text: str | None = None
    company_url: str | None = None
    company_domain: str | None = None
    company_logo_url: str | None = None
    country: str | None = None
    country_code: str | None = None
    city: str | None = None
    region: str | None = None
    work_mode: str | None = None
    employment_type: str | None = None
    category: str | None = None
    seniority: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    currency: str | None = None
    posted_at: datetime | None = None
    language: str = "en"
    source_flag: bool | None = None
    volunteer: VolunteerFields | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.title = (self.title or "").strip()[:500]
        self.company = (self.company or "").strip()[:300]
        self.apply_url = strip_tracking((self.apply_url or "").strip())
        if self.description_html:
            self.description_html = sanitize_html(self.description_html)
        if not self.description_text and self.description_html:
            self.description_text = html_to_text(self.description_html)
        if self.description_text:
            self.description_text = self.description_text[:12000]
        if not self.description_html and self.description_text:
            self.description_html = f"<p>{self.description_text}</p>"
        if not self.language:
            self.language = detect_language(self.description_text or self.title)
        if not self.company_domain:
            self.company_domain = domain_from_url(self.company_url, AGGREGATOR_DOMAINS)
        if not self.category:
            self.category = detect_category(self.title, self.description_text, self.extras.get("tags"))
        if not self.work_mode:
            self.work_mode = detect_work_mode(
                f"{self.title} {self.description_text or ''}", "remote" if self.extras.get("remote") else None
            )
        if not self.employment_type:
            self.employment_type = detect_employment_type(
                self.title, self.extras.get("employment_type"), default="full_time"
            )
        if not self.seniority:
            self.seniority = detect_seniority(self.title, self.description_text)

    def finalize_country(self) -> None:
        if not self.country_code and (self.country or self.city or self.extras.get("location")):
            code, name = detect_country(self.country, self.city, self.extras.get("location"))
            self.country_code = self.country_code or code
            self.country = self.country or name
        if not self.city and self.extras.get("city"):
            self.city = self.extras["city"]
        if self.company_domain is None:
            self.company_domain = domain_from_url(self.apply_url, AGGREGATOR_DOMAINS)

    @property
    def search_text(self) -> str:
        bits = [
            self.title, self.company, self.city, self.country, self.category,
            self.employment_type, self.extras.get("tags"), excerpt(self.description_text, 4000),
        ]
        return fold_text(" ".join(str(b) for b in bits if b))


class SourceError(RuntimeError):
    pass


def make_client(timeout: float = 15.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=8.0),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"},
        limits=httpx.Limits(max_connections=12, max_keepalive_connections=6),
    )


def salary_from_fields(
    min_value, max_value, currency: str | None, text: str | None = None, country_code: str | None = None
) -> tuple[float | None, float | None, str | None]:
    def number(value):
        try:
            return float(str(value).replace(",", "").replace(" ", ""))
        except (TypeError, ValueError):
            return None

    low, high = number(min_value), number(max_value)
    if low is None and high is None and text:
        low, high, currency = parse_salary(text, currency)
    return low, high, currency


def iso_date(value) -> datetime | None:
    return parse_date(value)
