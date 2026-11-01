"""Refresh official sponsor-register cache files.

Usage: python scripts/refresh_registers.py [--force]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.visa.registers import refresh_uk_register_if_stale  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh official sponsor registers")
    parser.add_argument("--force", action="store_true", help="download even if the cache is fresh")
    args = parser.parse_args()
    result = refresh_uk_register_if_stale(max_age_days=0 if args.force else 7)
    print(f"UK Home Office register: {result['reason']} ({result['entries']} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
