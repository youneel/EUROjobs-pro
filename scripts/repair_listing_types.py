"""Keep job-board listings out of the volunteer board.

Earlier ingestion promoted any job advert that mentioned volunteering somewhere
in its description. This repairs those rows by moving them back to jobs when the
title does not describe a volunteer role and the source is not a volunteer feed.

Usage:
    python scripts/repair_listing_types.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Listing, VolunteerDetails  # noqa: E402
from app.visa.classifier import VOLUNTEER_HINTS  # noqa: E402

VOLUNTEER_SOURCES = {"reliefweb"}


def main() -> int:
    moved = 0
    with SessionLocal() as db:
        rows = db.scalars(
            select(Listing).where(Listing.listing_type == "volunteer")
        ).all()
        for listing in rows:
            if listing.source_name in VOLUNTEER_SOURCES:
                continue
            if VOLUNTEER_HINTS.search(listing.title or ""):
                continue
            listing.listing_type = "job"
            db.execute(
                delete(VolunteerDetails).where(VolunteerDetails.listing_id == listing.id)
            )
            moved += 1
        db.commit()
    print(f"Moved {moved} listing(s) from volunteer back to jobs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
