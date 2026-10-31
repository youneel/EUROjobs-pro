"""Apply-link resolution and background validation."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import session_scope
from app.models import Listing
from app.security import is_safe_url, safe_fetch
from app.utils import normalize_url, strip_tracking

log = logging.getLogger(__name__)

DEAD_TEXT = [
    r"job (?:is )?no longer available", r"position (?:has been )?filled",
    r"no longer accepting applications", r"this job has expired", r"vacancy (?:is )?closed",
    r"job posting (?:has )?expired", r"applications? (?:are )?closed",
    r"offre (?:d'emploi )?(?:expir[ée]e|n'est plus disponible)", r"poste (?:d[ée]j[àa] )?pourvu",
    r"cette offre n'est plus disponible", r"les candidatures sont closes",
    r"انتهت صلاحية (?:هذا )?الإعلان", r"لم يعد هذا الإعلان متاح", r"تم إغلاق (?:هذا )?الإعلان",
    r"تم شغل (?:هذا )?المنصب", r"لم يعد التقديم متاح",
]

_DEAD_IMPORT = None


def _dead_patterns():
    global _DEAD_IMPORT
    if _DEAD_IMPORT is None:
        import re

        _DEAD_IMPORT = [re.compile(p, re.I) for p in DEAD_TEXT]
    return _DEAD_IMPORT


def _looks_dead(body: str) -> bool:
    sample = body[:80_000]
    return any(pattern.search(sample) for pattern in _dead_patterns())


async def validate_url(url: str, *, deep: bool = True) -> tuple[bool, str, str]:
    """Return (ok, final_url, reason). Network errors are inconclusive, not dead."""
    url = strip_tracking(url or "")
    if not url:
        return False, "", "missing URL"
    ok, reason = is_safe_url(url, allow_ports={80, 443})
    if not ok:
        return False, url, reason

    response, body, error = await safe_fetch(url, method="HEAD", max_bytes=200_000, allow_ports={80, 443})
    if error and "fetch failed" in error:
        # HEAD may be refused; retry with GET before drawing conclusions.
        response, body, error = await safe_fetch(url, method="GET", max_bytes=350_000, allow_ports={80, 443})
    if response is None:
        return False, url, error or "unreachable"

    final_url = str(response.url)
    if response.status_code in {404, 410}:
        return False, final_url, f"HTTP {response.status_code}"
    if response.status_code >= 400:
        return False, final_url, f"HTTP {response.status_code}"
    if deep and response.status_code == 200 and body:
        text = body.decode(response.encoding or "utf-8", errors="ignore")
        if _looks_dead(text):
            return False, final_url, "page says the vacancy is closed"
    return True, final_url, ""


async def revalidate_listing(listing: Listing) -> bool:
    ok, final, reason = await validate_url(listing.apply_url_final or listing.apply_url_original or "")
    listing.last_checked_at = datetime.now(timezone.utc)
    if ok:
        if final and final != listing.apply_url_final:
            listing.apply_url_final = normalize_url(final) or final
        listing.is_active = True
        return True
    # Only a definitive answer hides the listing; a flaky network must not.
    if reason.startswith("HTTP 4") or "closed" in reason or "expired" in reason or "blocked" in reason:
        listing.is_active = False
    return False


async def check_overdue(limit: int = 40) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    with session_scope() as db:
        rows = db.scalars(
            select(Listing)
            .where(
                Listing.is_active.is_(True),
                (Listing.last_checked_at.is_(None)) | (Listing.last_checked_at < cutoff),
            )
            .order_by(Listing.last_checked_at.asc().nullsfirst())
            .limit(limit)
        ).all()
        checked = dead = 0
        for row in rows:
            try:
                if await revalidate_listing(row):
                    checked += 1
                else:
                    dead += 1
            except Exception as exc:  # pragma: no cover
                log.debug("Link check failed for %s: %s", row.public_id, exc)
    return {"checked": checked, "dead": dead}
