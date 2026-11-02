"""Feed ingestion: fetch adapters concurrently, classify, deduplicate, persist."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import session_scope
from app.models import Listing, SourceRun, VolunteerDetails
from app.sources.base import NormalizedListing, make_client
from app.sources.registry import all_sources, live_sources
from app.utils import dedupe_hash, fold_text, normalize_url, url_hash
from app.visa.classifier import (
    classify_job,
    classify_volunteer,
    detect_fee,
    detect_scam,
    is_volunteer_posting,
)

log = logging.getLogger(__name__)


async def run_ingestion(source_names: list[str] | None = None, pages: int | None = None) -> dict:
    """Fetch every enabled source concurrently. One failing source never stops others."""
    sources = all_sources()
    if source_names:
        sources = [s for s in sources if s.name in source_names]
    totals = {"sources": 0, "fetched": 0, "accepted": 0, "errors": 0}
    async with make_client(timeout=25.0) as client:
        tasks = {asyncio.create_task(_run_source(source, client, pages)): source for source in sources}
        for coro in asyncio.as_completed(tasks):
            result = await coro
            totals["sources"] += 1
            totals["fetched"] += result.get("fetched", 0)
            totals["accepted"] += result.get("accepted", 0)
            totals["errors"] += 1 if result.get("error") else 0
    return totals


async def _run_source(source, client: httpx.AsyncClient, pages: int | None) -> dict:
    started = datetime.now(timezone.utc)
    fetched = accepted = 0
    error = None
    try:
        if source.name == "arbeitnow":
            items = await source.fetch(client, pages=pages or 4)
        else:
            items = await source.fetch(client)
        fetched = len(items)
        accepted = persist_items(items)
    except Exception as exc:  # adapters already catch; this is the last line
        error = str(exc)[:800]
        log.warning("Source %s failed: %s", source.name, exc)
    try:
        with session_scope() as db:
            db.add(
                SourceRun(
                    source_name=source.name,
                    started_at=started,
                    finished_at=datetime.now(timezone.utc),
                    status="error" if error else "ok",
                    fetched=fetched,
                    accepted=accepted,
                    error=error,
                )
            )
    except Exception:  # pragma: no cover
        log.exception("Could not record source run for %s", source.name)
    return {"source": source.name, "fetched": fetched, "accepted": accepted, "error": error}


def persist_items(items: list[NormalizedListing]) -> int:
    if not items:
        return 0
    accepted = 0
    with session_scope() as db:
        for item in items:
            try:
                with db.begin_nested():
                    if _persist_one(db, item):
                        accepted += 1
            except Exception as exc:  # pragma: no cover - defensive
                log.debug("Could not persist %s: %s", item.apply_url, exc)
        db.flush()
    return accepted


def _persist_one(db: Session, item: NormalizedListing) -> bool:
    item.finalize_country()
    if not item.apply_url.startswith(("http://", "https://")):
        return False
    if not item.title or not item.company:
        return False

    listing_type = item.listing_type
    # Only promote a job-board posting to a volunteer placement when the title
    # itself says so. A passing mention of "volunteer" in a long job advert
    # (company volunteering days, CSR copy) must not move the listing into the
    # volunteer board.
    if listing_type != "volunteer" and is_volunteer_posting(
        item.title, None, item.employment_type
    ):
        listing_type = "volunteer"

    # Classify before saving: listings without evidence never enter the board.
    if listing_type == "volunteer":
        result = classify_volunteer(
            title=item.title,
            organisation=item.company,
            description=item.description_text,
            country_code=item.country_code,
            source_flag=item.source_flag,
        )
    else:
        result = classify_job(
            title=item.title,
            company=item.company,
            description=item.description_text,
            country_code=item.country_code,
            source_flag=item.source_flag,
            source_name=item.source_name,
        )
    if result.tier not in {1, 2}:
        return False

    fee_required = False
    fee_amount = fee_currency = None
    scam_flags: list[str] = []
    if listing_type == "volunteer":
        fee_required, fee_amount, fee_currency = detect_fee(item.description_text)
        scam_flags = detect_scam(item.description_text)

    merged_hash = dedupe_hash(item.title, item.company, item.city)
    existing = db.scalar(
        select(Listing).where(
            (Listing.dedupe_hash == merged_hash) | (Listing.url_hash == url_hash(item.apply_url))
        )
    )
    if existing:
        # Keep the best record: prefer Tier 1, then newer, then richer text.
        if result.tier < existing.visa_tier:
            return False
        existing.last_checked_at = datetime.now(timezone.utc)
        existing.is_active = True
        if result.tier > existing.visa_tier or not existing.visa_evidence:
            existing.visa_tier = result.tier
            existing.visa_evidence = result.evidence
            existing.visa_checked_at = datetime.now(timezone.utc)
        if len(item.description_text or "") > len(existing.description_text or ""):
            existing.description_text = item.description_text
            existing.description_html = item.description_html
        if item.company_logo_url and not existing.company_logo_url:
            existing.company_logo_url = item.company_logo_url
        if item.posted_at and (not existing.posted_at or item.posted_at > existing.posted_at):
            existing.posted_at = item.posted_at
        return False

    listing = Listing(
        listing_type=listing_type,
        title=item.title,
        company=item.company,
        company_url=item.company_url,
        company_domain=item.company_domain,
        company_logo_url=item.company_logo_url,
        description_html=item.description_html,
        description_text=item.description_text,
        country=item.country,
        country_code=item.country_code,
        city=item.city,
        region=item.region,
        work_mode=item.work_mode,
        employment_type=item.employment_type,
        category=item.category,
        seniority=item.seniority,
        salary_min=item.salary_min,
        salary_max=item.salary_max,
        currency=item.currency,
        language=item.language,
        posted_at=item.posted_at,
        apply_url_original=item.apply_url,
        apply_url_final=normalize_url(item.apply_url) or item.apply_url,
        source_name=item.source_name,
        source_job_id=item.source_job_id,
        visa_tier=result.tier,
        visa_evidence=result.evidence,
        visa_type_hint=result.visa_type_hint,
        visa_checked_at=datetime.now(timezone.utc),
        dedupe_hash=merged_hash,
        url_hash=url_hash(item.apply_url),
        search_text=item.search_text,
        extras=item.extras,
    )
    db.add(listing)
    db.flush()

    if listing_type == "volunteer":
        volunteer = item.volunteer or VolunteerFieldsFactory(item)
        db.add(
            VolunteerDetails(
                listing_id=listing.id,
                duration=volunteer.duration,
                start_date=volunteer.start_date,
                application_deadline=volunteer.application_deadline,
                hours_per_week=volunteer.hours_per_week,
                cause_area=volunteer.cause_area,
                org_type=volunteer.org_type,
                skills_required=volunteer.skills_required,
                languages_required=volunteer.languages_required,
                min_age=volunteer.min_age,
                remote_volunteering=volunteer.remote_volunteering or item.work_mode == "remote",
                accommodation_provided=volunteer.accommodation_provided,
                meals_provided=volunteer.meals_provided,
                stipend=volunteer.stipend,
                stipend_currency=volunteer.stipend_currency,
                travel_covered=volunteer.travel_covered,
                insurance_provided=volunteer.insurance_provided,
                fee_required=fee_required or volunteer.fee_required,
                fee_amount=volunteer.fee_amount or fee_amount,
                fee_currency=volunteer.fee_currency or fee_currency,
                visa_support_type=volunteer.visa_support_type,
                programme_name=volunteer.programme_name,
                scam_flags=scam_flags,
            )
        )
    return True


def VolunteerFieldsFactory(item: NormalizedListing):  # noqa: N802 - factory name for readability
    from app.sources.base import VolunteerFields
    from app.utils import detect_category

    return VolunteerFields(
        cause_area=detect_category(item.title, item.description_text),
        org_type=item.extras.get("organization_type"),
        remote_volunteering=item.work_mode == "remote",
        programme_name=item.company,
        scam_flags=detect_scam(item.description_text),
    )


async def live_augment(query: str, limit_seconds: float = 5.0) -> list[dict]:
    """Query live sources in parallel with a hard timeout, classify and save."""
    if not query.strip():
        return []
    collected: list[NormalizedListing] = []
    async with make_client(timeout=limit_seconds) as client:
        tasks = [asyncio.create_task(src.search(client, query)) for src in live_sources()]
        done, pending = await asyncio.wait(tasks, timeout=limit_seconds)
        for task in pending:
            task.cancel()
        for task in done:
            try:
                collected.extend(task.result() or [])
            except Exception:
                continue
    if not collected:
        return []
    persist_items(collected)
    # Return the stored rows that are still active.
    hashes = [dedupe_hash(i.title, i.company, i.city) for i in collected]
    with session_scope() as db:
        rows = db.scalars(
            select(Listing).where(Listing.dedupe_hash.in_(hashes), Listing.is_active.is_(True))
        ).all()
        return [row_to_card(row) for row in rows]


def row_to_card(row: Listing) -> dict:
    from app.utils import logo_or_fallback

    return {
        "id": row.public_id,
        "type": row.listing_type,
        "title": row.title,
        "company": row.company,
        "city": row.city,
        "country": row.country,
        "country_code": row.country_code,
        "work_mode": row.work_mode,
        "employment_type": row.employment_type,
        "salary_min": row.salary_min,
        "salary_max": row.salary_max,
        "currency": row.currency,
        "posted_at": row.posted_at.isoformat() if row.posted_at else None,
        "visa_tier": row.visa_tier,
        "logo": logo_or_fallback(row.logo_path, row.country_code, row.logo_kind),
        "source": row.source_name,
        "apply_url": f"/go/{row.public_id}",
    }
