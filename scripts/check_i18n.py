"""Check that every translation key used by templates exists in all catalogues."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TEMPLATES = ROOT / "app" / "templates"
I18N = ROOT / "data" / "i18n"
PATTERN = re.compile(r"t\(\s*['\"]([a-z0-9_.]+)['\"]", re.I)
DYNAMIC = re.compile(r"t\(\s*['\"]([a-z0-9_.]+)['\"]\s*\+", re.I)


def main() -> int:
    used: set[str] = set()
    for path in TEMPLATES.glob("*.html"):
        text = path.read_text(encoding="utf-8")
        used.update(PATTERN.findall(text))
    catalogues = {}
    for lang in ("en", "fr", "ar"):
        catalogues[lang] = json.loads((I18N / f"{lang}.json").read_text(encoding="utf-8"))

    en = catalogues["en"]
    from app.data import CAUSE_AREAS, CATEGORIES, ORG_TYPES
    from app.utils import SENIORITY_PATTERNS

    dynamic_prefixes = {
        "category.": CATEGORIES,
        "cause.": CAUSE_AREAS,
        "org.": ORG_TYPES,
        "mode.": ["remote", "hybrid", "onsite"],
        "employment.": [
            "full_time", "part_time", "contract", "temporary", "internship", "apprenticeship"
        ],
        "seniority.": [key for key, _ in SENIORITY_PATTERNS],
        "docgen.tone_": ["professional", "friendly", "confident", "concise"],
        "docgen.style_": ["international", "us", "uk", "de", "fr", "ar"],
    }
    for prefix in list(dynamic_prefixes):
        if prefix in used:
            used.discard(prefix)
            for value in dynamic_prefixes[prefix]:
                used.add(f"{prefix}{value}")
    used.discard("ok")
    used.discard("err")
    missing = sorted(k for k in used if k not in en)
    print(f"{len(used)} static keys referenced in templates")
    if missing:
        print("MISSING static keys:")
        for key in missing:
            print("  ", key)
    failures = bool(missing)
    for lang in ("fr", "ar"):
        gaps = sorted(k for k in en if k not in catalogues[lang])
        extras = sorted(k for k in catalogues[lang] if k not in en)
        if gaps:
            failures = True
            print(f"MISSING in {lang}: {len(gaps)}")
            for key in gaps[:20]:
                print("  ", key)
        if extras:
            failures = True
            print(f"UNEXPECTED in {lang}: {len(extras)}")
            for key in extras[:20]:
                print("  ", key)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
