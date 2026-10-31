"""Company logo resolution and local caching.

Chain (first valid wins):
  1. logo URL supplied by the source
  2. optional logo service (LOGO_SERVICE_TOKEN)
  3. the employer's own site: apple-touch-icon, largest icon, og:image, favicon
  4. country flag / region icon fallback (handled by the template)

Everything is downloaded with the SSRF guard, validated as a real image, and
normalised to a 128x128 PNG served from our own domain. External SVGs are never
served raw.
"""
from __future__ import annotations

import hashlib
import io
import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.db import session_scope
from app.models import CompanyLogo, Listing
from app.security import is_safe_url, safe_fetch
from app.utils import domain_from_url, flag_url, fold_text, normalize_company, region_icon

log = logging.getLogger(__name__)

MAX_BYTES = 500_000
MIN_PX = 32
TARGET = 128
ICON_RE = re.compile(
    r"<link[^>]+rel=[\"'](?:apple-touch-icon(?:-precomposed)?|icon|shortcut icon)[\"'][^>]*>",
    re.I,
)
OG_RE = re.compile(
    r"<meta[^>]+property=[\"']og:image[\"'][^>]+content=[\"']([^\"']+)[\"']", re.I
)
HREF_RE = re.compile(r"href=[\"']([^\"']+)[\"']", re.I)
SIZE_RE = re.compile(r"sizes=[\"'](\d+)x(\d+)[\"']", re.I)


def company_key(company: str, domain: str | None = None) -> str:
    return f"{normalize_company(company)}|{(domain or '').lower()}"


def _store_image(data: bytes) -> str | None:
    if len(data) > MAX_BYTES:
        return None
    try:
        probe = Image.open(io.BytesIO(data))
        probe.verify()
        image = Image.open(io.BytesIO(data))
    except (UnidentifiedImageError, OSError):
        return None
    if image.width < MIN_PX or image.height < MIN_PX:
        return None
    image = image.convert("RGBA")
    # Reject blank images (one solid colour).
    colors = image.convert("RGB").getcolors(maxcolors=4096)
    if colors and len(colors) <= 1:
        return None
    # Normalise onto a transparent square canvas.
    image.thumbnail((TARGET, TARGET), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (TARGET, TARGET), (0, 0, 0, 0))
    canvas.paste(image, ((TARGET - image.width) // 2, (TARGET - image.height) // 2), image)
    digest = hashlib.sha256(data).hexdigest()[:24]
    filename = f"{digest}.png"
    target = settings.logo_dir / filename
    canvas.save(target, format="PNG", optimize=True)
    return f"/static/logos/{filename}"


async def _download_image(url: str) -> str | None:
    if not url or not url.startswith(("http://", "https://")):
        return None
    if url.lower().endswith(".svg") or "image/svg" in url.lower():
        return None  # never serve an external SVG raw
    response, data, error = await safe_fetch(
        url, method="GET", max_bytes=MAX_BYTES, allow_ports={80, 443}
    )
    if error or response is None or response.status_code >= 400 or not data:
        return None
    content_type = (response.headers.get("content-type") or "").lower()
    if content_type and not content_type.startswith("image/"):
        return None
    if "svg" in content_type:
        return None
    return _store_image(data)


async def _from_website(domain: str) -> str | None:
    if not domain:
        return None
    base = f"https://{domain}"
    response, body, error = await safe_fetch(
        base + "/", method="GET", max_bytes=350_000, allow_ports={80, 443}
    )
    candidates: list[str] = []
    if response is not None and body:
        html = body.decode(response.encoding or "utf-8", errors="ignore")
        for tag in ICON_RE.findall(html):
            href = HREF_RE.search(tag)
            if href:
                candidates.append(urljoin(str(response.url), href.group(1)))
            size = SIZE_RE.search(tag)
            if size and int(size.group(1)) < MIN_PX:
                candidates.pop()
        og = OG_RE.search(html)
        if og:
            candidates.append(urljoin(str(response.url), og.group(1)))
    candidates.extend([f"{base}/apple-touch-icon.png", f"{base}/favicon.ico"])
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        path = await _download_image(candidate)
        if path:
            return path
    return None


async def _from_service(domain: str) -> str | None:
    if not settings.logo_service_token or not domain:
        return None
    url = settings.logo_service_url.format(domain=domain, token=settings.logo_service_token)
    # Do not leak the token in logs.
    return await _download_image(url)


def _fallback_kind(country_code: str | None) -> str:
    return "country" if country_code else "region"


def fallback_for(country_code: str | None) -> str:
    return flag_url(country_code) if country_code else region_icon(None)


async def resolve_company(
    db: Session,
    *,
    company: str,
    domain: str | None,
    source_logo_url: str | None,
    country_code: str | None,
) -> CompanyLogo:
    key = company_key(company, domain)
    record = db.scalar(select(CompanyLogo).where(CompanyLogo.key == key))
    if record is None:
        record = CompanyLogo(key=key, company=company, domain=domain)
        db.add(record)
        db.flush()

    if record.logo_path and record.checked_at and record.checked_at > datetime.now(timezone.utc) - timedelta(
        days=settings.logo_refresh_days
    ):
        return record

    record.attempts += 1
    path = None
    if source_logo_url:
        path = await _download_image(source_logo_url)
    if not path and domain:
        path = await _from_service(domain)
    if not path and domain:
        path = await _from_website(domain)

    if path:
        record.logo_path = path
        record.logo_kind = "company"
    else:
        record.logo_path = None
        record.logo_kind = _fallback_kind(country_code)
    record.checked_at = datetime.now(timezone.utc)
    db.flush()

    # Update every listing that shares this employer.
    stmt = select(Listing).where(
        (Listing.company_domain == domain) if domain else (Listing.company == company)
    )
    for listing in db.scalars(stmt).all():
        listing.logo_path = record.logo_path
        listing.logo_kind = record.logo_kind
    return record


async def resolve_pending(limit: int = 20) -> dict:
    """Background worker: resolve logos for companies with no fresh result."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.logo_refresh_days)
    resolved = 0
    with session_scope() as db:
        rows = db.execute(
            select(Listing.company, Listing.company_domain, Listing.company_logo_url, Listing.country_code)
            .where(Listing.is_active.is_(True), Listing.visa_tier.in_([1, 2]))
            .group_by(Listing.company, Listing.company_domain)
            .limit(limit * 4)
        ).all()
        seen = set()
        for company, domain, source_logo, country in rows:
            if not company:
                continue
            key = company_key(company, domain)
            if key in seen:
                continue
            seen.add(key)
            record = db.scalar(select(CompanyLogo).where(CompanyLogo.key == key))
            if record and record.checked_at and record.checked_at > cutoff:
                continue
            try:
                await resolve_company(
                    db, company=company, domain=domain, source_logo_url=source_logo,
                    country_code=country,
                )
                resolved += 1
            except Exception as exc:  # pragma: no cover
                log.debug("Logo resolution failed for %s: %s", company, exc)
            if resolved >= limit:
                break
    return {"resolved": resolved}


def logo_for_listing(listing: Listing) -> str:
    if listing.logo_path:
        return listing.logo_path
    return fallback_for(listing.country_code)


def logo_alt_key(listing: Listing) -> str:
    if listing.logo_path:
        return "logo.company_alt"
    if listing.country_code:
        return "logo.flag_alt"
    return "logo.region_alt"
