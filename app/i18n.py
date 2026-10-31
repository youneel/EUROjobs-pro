"""Lightweight JSON-catalogue i18n with RTL and plural support.

The catalogues live in ``data/i18n/{lang}.json``. Every user-facing string in
templates, JavaScript (served through ``/i18n/<lang>.js``) and API errors comes
from these files. A completeness test enforces that ar/fr/en stay in sync.

Dates, numbers and plurals use Babel/CLDR. Digits are always Western (0-9).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from babel import Locale
from babel.dates import format_date, format_datetime, format_timedelta, format_time
from babel.numbers import format_currency, format_decimal

from app.config import I18N_DIR, settings

RTL_LANGUAGES = {"ar", "fa", "he", "ur"}
LANGUAGE_NAMES = {"en": "English", "fr": "Français", "ar": "العربية"}

# Eastern Arabic-Indic digits -> Western digits. The spec requires Western
# digits in all three languages, even inside Arabic text.
_DIGIT_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def western_digits(value: str) -> str:
    return value.translate(_DIGIT_MAP)


def is_rtl(lang: str) -> bool:
    return (lang or "en").split("-")[0] in RTL_LANGUAGES


def normalize_lang(value: str | None, fallback: str | None = None) -> str:
    allowed = settings.languages
    if value:
        low = value.lower().replace("_", "-")
        base = low.split("-")[0]
        if base in allowed:
            return base
    return fallback if fallback in allowed else settings.default_language


@lru_cache
def load_catalog(lang: str) -> dict[str, str]:
    path: Path = I18N_DIR / f"{lang}.json"
    if not path.exists():
        path = I18N_DIR / f"{settings.default_language}.json"
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


class Translator:
    def __init__(self, lang: str):
        self.lang = normalize_lang(lang)
        self.catalog = load_catalog(self.lang)
        self.fallback = load_catalog(settings.default_language)
        try:
            self.locale = Locale.parse(self.lang)
        except Exception:  # pragma: no cover - defensive
            self.locale = Locale.parse(settings.default_language)

    def t(self, key: str, **kwargs) -> str:
        text = self.catalog.get(key)
        if text is None:
            text = self.fallback.get(key, key)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                pass
        return western_digits(text)

    def tn(self, key: str, n: int | float, **kwargs) -> str:
        """Plural-aware translation: resolves key.<plural-form> then key.other."""
        cat = self.locale.plural_form(int(n)) if float(n).is_integer() else "other"
        text = self.catalog.get(f"{key}.{cat}") or self.fallback.get(f"{key}.{cat}")
        if text is None:
            text = self.catalog.get(f"{key}.other") or self.fallback.get(f"{key}.other")
        if text is None:
            return self.t(key, n=n, count=n, **kwargs)
        try:
            return western_digits(text.format(n=n, count=n, **kwargs))
        except (KeyError, IndexError, ValueError):
            return western_digits(text)

    def date(self, value, fmt: str = "medium") -> str:
        if not value:
            return ""
        try:
            return western_digits(format_date(value, format=fmt, locale=self.locale))
        except Exception:
            return western_digits(str(value))

    def datetime(self, value, fmt: str = "medium") -> str:
        if not value:
            return ""
        try:
            return western_digits(format_datetime(value, format=fmt, locale=self.locale))
        except Exception:
            return western_digits(str(value))

    def time(self, value) -> str:
        try:
            return western_digits(format_time(value, locale=self.locale))
        except Exception:
            return ""

    def relative(self, value) -> str:
        if not value:
            return ""
        from datetime import datetime, timezone

        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        delta = value - datetime.now(timezone.utc)
        try:
            return western_digits(format_timedelta(delta, add_direction=True, locale=self.locale))
        except Exception:
            return self.date(value)

    def number(self, value, decimals: int = 0) -> str:
        if value is None:
            return ""
        try:
            return western_digits(
                format_decimal(value, locale=self.locale, decimal_quantization=bool(decimals))
            )
        except Exception:
            return western_digits(str(value))

    def money(self, amount, currency: str | None) -> str:
        if amount is None:
            return ""
        if not currency:
            return self.number(amount)
        try:
            return western_digits(format_currency(amount, currency, locale=self.locale))
        except Exception:
            return f"{self.number(amount)} {currency}"

    def country(self, code: str | None) -> str:
        if not code:
            return ""
        try:
            return self.locale.territories.get(code.upper(), code.upper())
        except Exception:
            return code.upper()

    def language_name(self, code: str) -> str:
        return LANGUAGE_NAMES.get(code, code)


def translator_for(lang: str | None) -> Translator:
    return Translator(lang or settings.default_language)


def catalog_js(lang: str) -> str:
    """Serialise a catalogue for the browser, safe inside a <script> tag."""
    cat = load_catalog(normalize_lang(lang))
    payload = json.dumps(cat, ensure_ascii=False, separators=(",", ":"))
    return payload.replace("</", "<\\/")
