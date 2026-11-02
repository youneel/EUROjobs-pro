"""Re-derive readable description text for listings already in the database.

Older versions of ``html_to_text`` removed block tags without a separator, so
stored snippets could join words across headings and paragraphs
("About usWe build..."), and some feeds left double-encoded punctuation behind
("â€”" instead of an em dash). This script rebuilds ``description_html`` and
``description_text`` from the stored employer copy, repairing both. It is safe
to run repeatedly.

Usage:
    python scripts/repair_descriptions.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Listing  # noqa: E402
from app.utils import html_to_text, prepare_description  # noqa: E402


def main() -> int:
    changed = 0
    inspected = 0
    with SessionLocal() as db:
        rows = db.scalars(select(Listing)).all()
        for listing in rows:
            inspected += 1
            html = prepare_description(listing.description_html or "")
            if not html:
                continue
            text = html_to_text(html)[:12000]
            if html != (listing.description_html or "") or text != (listing.description_text or ""):
                listing.description_html = html
                listing.description_text = text
                changed += 1
        db.commit()
    print(f"Inspected {inspected} listings; repaired {changed} description texts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
