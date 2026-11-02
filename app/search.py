"""Database-first search. Answers from SQLite/Postgres in milliseconds.

Jobs and volunteers are a hard partition: every query filters ``listing_type``
before anything else, so the two sections can never mix.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.data import CATEGORIES, CAUSE_AREAS, ORG_TYPES, synonyms_for
from app.models import Listing, VolunteerDetails
from app.utils import (
    category_of,
    excerpt,
    flag_url,
    logo_or_fallback,
    normalize_query,
    region_icon,
)

MAX_PAGE_SIZE = 60


@dataclass
class SearchFilters:
    listing_type: str = "job"
    q: str = ""
    country: str = ""
    city: str = ""
    category: str = ""
    employment_type: str = ""
    work_mode: str = ""
    seniority: str = ""
    salary_min: float | None = None
    posted_days: int | None = None
    visa_tier: int | None = None
    source: str = ""
    sort: str = "newest"
    page: int = 1
    page_size: int = 24
    # volunteer-specific
    cause: str = ""
    org_type: str = ""
    remote_volunteering: bool = False
    accommodation: bool = False
    meals: bool = False
    stipend: bool = False
    travel: bool = False
    insurance: bool = False
    include_fee: bool = False
    min_age: int | None = None
    language: str = ""
    extra_tokens: list[str] = field(default_factory=list)

    @classmethod
    def from_query(cls, params: dict) -> "SearchFilters":
        def pick(*keys, default=""):
            for key in keys:
                value = params.get(key)
                if value not in (None, ""):
                    return value
            return default

        def as_int(value):
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        def as_bool(value):
            return str(value).lower() in {"1", "true", "yes", "on"}

        def as_float(value):
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        listing_type = "volunteer" if pick("type", "listing_type") == "volunteer" else "job"
        page_size = as_int(pick("page_size", default=24)) or 24
        posted = as_int(pick("posted_days", "posted"))
        tier = as_int(pick("visa_tier", "tier"))
        return cls(
            listing_type=listing_type,
            q=str(pick("q", "query", "keyword")).strip()[:200],
            country=str(pick("country")).lower()[:2],
            city=str(pick("city")).strip()[:120],
            category=str(pick("category")).strip().lower(),
            employment_type=str(pick("employment_type", "employment")).strip().lower(),
            work_mode=str(pick("work_mode", "mode")).strip().lower(),
            seniority=str(pick("seniority")).strip().lower(),
            salary_min=as_float(pick("salary_min", "salary")),
            posted_days=posted if posted and posted > 0 else None,
            visa_tier=tier if tier in {1, 2} else None,
            source=str(pick("source")).strip()[:60],
            sort="relevance" if pick("sort") == "relevance" else "newest",
            page=max(1, as_int(pick("page", default=1)) or 1),
            page_size=max(1, min(MAX_PAGE_SIZE, page_size)),
            cause=str(pick("cause")).strip().lower(),
            org_type=str(pick("org_type")).strip().lower(),
            remote_volunteering=as_bool(pick("remote_volunteering", "remote")),
            accommodation=as_bool(pick("accommodation")),
            meals=as_bool(pick("meals")),
            stipend=as_bool(pick("stipend")),
            travel=as_bool(pick("travel")),
            insurance=as_bool(pick("insurance")),
            include_fee=as_bool(pick("include_fee")),
            min_age=as_int(pick("min_age")),
            language=str(pick("language")).strip()[:8],
            extra_tokens=[str(t) for t in params.get("extra_tokens", [])][:8],
        )

    def query_params(self, **overrides) -> dict:
        data = {
            "q": self.q, "country": self.country, "city": self.city, "category": self.category,
            "employment_type": self.employment_type, "work_mode": self.work_mode,
            "seniority": self.seniority, "salary_min": self.salary_min,
            "posted_days": self.posted_days, "visa_tier": self.visa_tier,
            "source": self.source, "sort": self.sort, "cause": self.cause,
            "org_type": self.org_type, "remote_volunteering": self.remote_volunteering,
            "accommodation": self.accommodation, "meals": self.meals,
            "stipend": self.stipend, "travel": self.travel, "insurance": self.insurance,
            "include_fee": self.include_fee, "min_age": self.min_age, "language": self.language,
        }
        data.update(overrides)
        return {k: v for k, v in data.items() if v not in (None, "", False) and k != "sort" or k == "sort"}


def _keyword_clause(q: str, extra_tokens: list[str] | None = None):
    tokens = [t for t in normalize_query(q).split() if t]
    for extra in extra_tokens or []:
        tokens.extend(t for t in normalize_query(extra).split() if t)
    tokens = tokens[:8]
    clauses = []
    for token in tokens:
        variants = {token, *synonyms_for(token)}
        clauses.append(
            or_(*[Listing.search_text.like(f"%{v}%") for v in variants if v])
        )
    return and_(*clauses) if clauses else None


def build_query(filters: SearchFilters):
    stmt = select(Listing).where(
        Listing.listing_type == filters.listing_type,
        Listing.is_active.is_(True),
        Listing.visa_tier.in_([1, 2]),
    )
    if filters.q or filters.extra_tokens:
        clause = _keyword_clause(filters.q, filters.extra_tokens)
        if clause is not None:
            stmt = stmt.where(clause)
    if filters.country:
        stmt = stmt.where(Listing.country_code == filters.country)
    if filters.city:
        stmt = stmt.where(Listing.city.ilike(f"%{filters.city}%"))
    if filters.category in CATEGORIES:
        stmt = stmt.where(Listing.category == filters.category)
    if filters.employment_type:
        stmt = stmt.where(Listing.employment_type == filters.employment_type)
    if filters.work_mode:
        stmt = stmt.where(Listing.work_mode == filters.work_mode)
    if filters.seniority:
        stmt = stmt.where(Listing.seniority == filters.seniority)
    if filters.visa_tier in {1, 2}:
        stmt = stmt.where(Listing.visa_tier == filters.visa_tier)
    if filters.source:
        stmt = stmt.where(Listing.source_name == filters.source)
    if filters.salary_min:
        stmt = stmt.where(
            or_(Listing.salary_max >= filters.salary_min, Listing.salary_min >= filters.salary_min)
        )
    if filters.posted_days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=filters.posted_days)
        stmt = stmt.where(Listing.posted_at >= cutoff)
    if filters.language:
        stmt = stmt.where(Listing.language == filters.language)

    if filters.listing_type == "volunteer":
        has_filters = any([
            filters.cause, filters.org_type, filters.remote_volunteering, filters.accommodation,
            filters.meals, filters.stipend, filters.travel, filters.insurance, filters.min_age,
            not filters.include_fee,
        ])
        if has_filters:
            stmt = stmt.join(VolunteerDetails, VolunteerDetails.listing_id == Listing.id, isouter=True)
        if filters.cause in CAUSE_AREAS:
            stmt = stmt.where(VolunteerDetails.cause_area == filters.cause)
        if filters.org_type in ORG_TYPES:
            stmt = stmt.where(VolunteerDetails.org_type == filters.org_type)
        if filters.remote_volunteering:
            stmt = stmt.where(
                or_(VolunteerDetails.remote_volunteering.is_(True), Listing.work_mode == "remote")
            )
        for flag, column in (
            (filters.accommodation, VolunteerDetails.accommodation_provided),
            (filters.meals, VolunteerDetails.meals_provided),
            (filters.travel, VolunteerDetails.travel_covered),
            (filters.insurance, VolunteerDetails.insurance_provided),
        ):
            if flag:
                stmt = stmt.where(column.is_(True))
        if filters.stipend:
            stmt = stmt.where(VolunteerDetails.stipend.is_not(None))
        if filters.min_age:
            stmt = stmt.where(
                or_(VolunteerDetails.min_age.is_(None), VolunteerDetails.min_age <= filters.min_age)
            )
        if not filters.include_fee:
            # Fee-charging programmes are hidden by default.
            stmt = stmt.where(
                or_(VolunteerDetails.fee_required.is_(False), VolunteerDetails.fee_required.is_(None))
            )
        stmt = stmt.where(or_(VolunteerDetails.scam_flags.is_(None), func.length(VolunteerDetails.scam_flags) < 3))

    if filters.sort == "relevance" and (filters.q or filters.extra_tokens):
        stmt = stmt.order_by(Listing.visa_tier.asc(), Listing.posted_at.desc().nullslast())
    else:
        stmt = stmt.order_by(Listing.posted_at.desc().nullslast(), Listing.created_at.desc())
    return stmt


def search_listings(db: Session, filters: SearchFilters) -> tuple[list[Listing], int]:
    base = build_query(filters)
    count_stmt = select(func.count()).select_from(base.order_by(None).subquery())
    total = int(db.scalar(count_stmt) or 0)
    rows = (
        db.scalars(
            base.options(joinedload(Listing.volunteer))
            .offset((filters.page - 1) * filters.page_size)
            .limit(filters.page_size)
        )
        .unique()
        .all()
    )
    return list(rows), total


def counter(db: Session, listing_type: str) -> dict:
    total = int(
        db.scalar(
            select(func.count()).select_from(Listing).where(
                Listing.listing_type == listing_type,
                Listing.is_active.is_(True),
                Listing.visa_tier.in_([1, 2]),
            )
        )
        or 0
    )
    countries = int(
        db.scalar(
            select(func.count(func.distinct(Listing.country_code))).where(
                Listing.listing_type == listing_type,
                Listing.is_active.is_(True),
                Listing.visa_tier.in_([1, 2]),
                Listing.country_code.is_not(None),
            )
        )
        or 0
    )
    return {"count": total, "countries": countries}


def facets(db: Session, listing_type: str) -> dict:
    countries = db.execute(
        select(Listing.country_code, func.max(Listing.country), func.count())
        .where(
            Listing.listing_type == listing_type,
            Listing.is_active.is_(True),
            Listing.visa_tier.in_([1, 2]),
            Listing.country_code.is_not(None),
        )
        .group_by(Listing.country_code)
        .order_by(func.count().desc())
        .limit(80)
    ).all()
    sources = db.execute(
        select(Listing.source_name, func.count())
        .where(Listing.listing_type == listing_type, Listing.is_active.is_(True))
        .group_by(Listing.source_name)
        .order_by(func.count().desc())
    ).all()
    return {
        "countries": [{"code": c, "name": n or c, "count": n2} for c, n, n2 in countries if c],
        "sources": [{"name": s, "count": c} for s, c in sources],
    }


def similar_listings(db: Session, listing: Listing, limit: int = 4) -> list[Listing]:
    stmt = (
        select(Listing)
        .where(
            Listing.listing_type == listing.listing_type,
            Listing.is_active.is_(True),
            Listing.visa_tier.in_([1, 2]),
            Listing.id != listing.id,
            or_(
                Listing.country_code == listing.country_code,
                Listing.category == listing.category,
            ),
        )
        .order_by(Listing.visa_tier.asc(), Listing.posted_at.desc().nullslast())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def card_dict(listing: Listing) -> dict:
    volunteer = listing.volunteer
    return {
        "id": listing.public_id,
        "type": listing.listing_type,
        "title": listing.title,
        "company": listing.company,
        "company_domain": listing.company_domain,
        "city": listing.city,
        "country": listing.country,
        "country_code": listing.country_code,
        "work_mode": listing.work_mode,
        "employment_type": listing.employment_type,
        "category": category_of(listing),
        "seniority": listing.seniority,
        "salary_min": listing.salary_min,
        "salary_max": listing.salary_max,
        "currency": listing.currency,
        "posted_at": listing.posted_at.isoformat() if listing.posted_at else None,
        "visa_tier": listing.visa_tier,
        "visa_evidence": excerpt(listing.visa_evidence, 320),
        "logo": logo_or_fallback(listing.logo_path, listing.country_code, listing.logo_kind),
        "logo_kind": listing.logo_kind or ("country" if listing.country_code else "region"),
        "source": listing.source_name,
        "apply_url": f"/go/{listing.public_id}",
        "detail_url": f"/{'volunteer' if listing.listing_type == 'volunteer' else 'jobs'}/{listing.public_id}",
        "description": excerpt(listing.description_html or listing.description_text, 220),
        "language": listing.language,
        "volunteer": (
            {
                "cause_area": volunteer.cause_area,
                "duration": volunteer.duration,
                "org_type": volunteer.org_type,
                "fee_required": volunteer.fee_required,
                "fee_amount": volunteer.fee_amount,
                "fee_currency": volunteer.fee_currency,
                "accommodation": volunteer.accommodation_provided,
                "meals": volunteer.meals_provided,
                "stipend": volunteer.stipend,
                "travel": volunteer.travel_covered,
                "insurance": volunteer.insurance_provided,
                "remote": volunteer.remote_volunteering,
                "visa_support_type": volunteer.visa_support_type,
                "scam_flags": volunteer.scam_flags,
            }
            if volunteer
            else None
        ),
    }


def compact_for_agent(listing: Listing) -> dict:
    return {
        "id": listing.public_id,
        "type": listing.listing_type,
        "title": listing.title,
        "company": listing.company,
        "country": listing.country or "Worldwide",
        "city": listing.city,
        "visa_tier": listing.visa_tier,
        "employment_type": listing.employment_type,
        "url": f"/{'volunteer' if listing.listing_type == 'volunteer' else 'jobs'}/{listing.public_id}",
        "apply_url": f"/go/{listing.public_id}",
        "summary": excerpt(listing.description_html or listing.description_text, 260),
    }


def fallback_logo(country_code: str | None) -> str:
    return flag_url(country_code) if country_code else region_icon(None)
