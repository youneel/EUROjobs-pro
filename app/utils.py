"""Text normalisation, classification heuristics and small helpers."""
from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import nh3

from app.config import STATIC_DIR
from app.data import COUNTRY_ALIASES, COUNTRIES, CATEGORIES, region_for

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")
_ARABIC_FOLD = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ئ": "ي", "ؤ": "و",
    "ة": "ه", "ﻻ": "لا", "ﻷ": "لا", "ﻹ": "لا", "ﻵ": "لا",
})
_LEGAL_SUFFIXES = re.compile(
    r"\b(ltd|limited|llc|inc|incorporated|corp|corporation|co|company|gmbh|ag|kg|ug|"
    r"bv|nv|sa|sas|sarl|srl|spa|plc|pte|pty|oy|ab|as|aps|sro|zrt|kft|doo|dod|"
    r"foundation|stiftung|group|holdings?)\b\.?",
    re.IGNORECASE,
)
_PUNCT = re.compile(r"[^\w\s\u0600-\u06FF]", re.UNICODE)
_WS = re.compile(r"\s+")


def fold_text(value: str | None) -> str:
    """Case-fold, strip accents and Arabic diacritics; keep letters/numbers."""
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.translate(_ARABIC_FOLD)
    text = _ARABIC_DIACRITICS.sub("", text)
    text = text.casefold()
    text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text, flags=re.UNICODE)
    return _WS.sub(" ", text).strip()


def normalize_company(value: str | None) -> str:
    if not value:
        return ""
    text = fold_text(value)
    text = _LEGAL_SUFFIXES.sub(" ", text)
    return _WS.sub(" ", text).strip()


def normalize_query(value: str | None) -> str:
    return fold_text(value)


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    text = nh3.clean(value, tags=set())
    text = html.unescape(text)
    return _WS.sub(" ", text).strip()


def sanitize_html(value: str | None) -> str:
    if not value:
        return ""
    return nh3.clean(
        value,
        tags={
            "p", "br", "ul", "ol", "li", "strong", "b", "em", "i", "u", "h1", "h2",
            "h3", "h4", "h5", "h6", "blockquote", "a", "hr", "table", "thead",
            "tbody", "tr", "th", "td", "span", "div", "code", "pre",
        },
        attributes={"a": {"href", "title", "rel", "target"}, "span": {"dir"}, "div": {"dir"}},
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer nofollow",
    )


def excerpt(value: str | None, length: int = 280) -> str:
    text = html_to_text(value)
    if len(text) <= length:
        return text
    cut = text[:length].rsplit(" ", 1)[0]
    return f"{cut}…"


# ---------------------------------------------------------------------------
# Hashing / URLs
# ---------------------------------------------------------------------------

def stable_hash(*parts: str | None) -> str:
    joined = "\x1f".join(fold_text(p) for p in parts if p)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def dedupe_hash(title: str | None, company: str | None, city: str | None) -> str:
    return stable_hash(normalize_company(company), fold_text(title), fold_text(city))


def url_hash(url: str | None) -> str:
    return stable_hash(normalize_url(url))


TRACKING_PREFIXES = ("utm_", "gclid", "fbclid", "mc_cid", "mc_eid", "ref", "referrer", "src")
TRACKING_KEYS = {"trk", "trackingid", "tracking_id", "source", "gh_src"}


def strip_tracking(url: str) -> str:
    try:
        parts = urlparse(url)
        query = [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not k.lower().startswith(TRACKING_PREFIXES) and k.lower() not in TRACKING_KEYS
        ]
        return urlunparse(parts._replace(query=urlencode(query)))
    except Exception:
        return url


def normalize_url(url: str | None) -> str:
    if not url:
        return ""
    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    if not re.match(r"^https?://", url, re.I):
        return ""
    parts = urlparse(url)
    host = (parts.hostname or "").lower().removeprefix("www.")
    path = parts.path.rstrip("/") or "/"
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return f"{parts.scheme.lower()}://{host}{path}{('?' + query) if query else ''}"


def domain_from_url(url: str | None, ignore: set[str] | None = None) -> str | None:
    if not url:
        return None
    try:
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    except Exception:
        return None
    if not host or "." not in host:
        return None
    if ignore and any(host == d or host.endswith("." + d) for d in ignore):
        return None
    return host


# ---------------------------------------------------------------------------
# Currency / salary / dates
# ---------------------------------------------------------------------------

CURRENCY_SYMBOLS = {
    "$": "USD", "€": "EUR", "£": "GBP", "CHF": "CHF", "C$": "CAD", "A$": "AUD",
    "¥": "JPY", "₹": "INR", "R$": "BRL", "kr": "SEK", "zł": "PLN", "₺": "TRY",
}

_SALARY_RE = re.compile(
    r"(?P<cur>USD|EUR|GBP|CHF|CAD|AUD|JPY|INR|BRL|PLN|SEK|NOK|DKK|AED|SAR|QAR|"
    r"CHF|\$|€|£|¥|₹|R\$)?\s*"
    r"(?P<min>\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?[kK]?)"
    r"(?:\s*(?:-|–|—|to|à|إلى)\s*"
    r"(?P<max>\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?[kK]?))?",
    re.IGNORECASE,
)


def _parse_amount(raw: str | None) -> float | None:
    if not raw:
        return None
    text = raw.replace(" ", "")
    multiplier = 1.0
    if text.lower().endswith("k"):
        multiplier = 1000.0
        text = text[:-1]
    # European 1.234,56 vs US 1,234.56
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif text.count(",") == 1 and len(text.split(",")[-1]) == 2:
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def parse_salary(text: str | None, default_currency: str | None = None) -> tuple[float | None, float | None, str | None]:
    if not text:
        return None, None, default_currency
    match = _SALARY_RE.search(text)
    if not match:
        return None, None, default_currency
    currency = match.group("cur")
    if currency:
        currency = CURRENCY_SYMBOLS.get(currency, currency).upper()
    else:
        currency = default_currency
    low = _parse_amount(match.group("min"))
    high = _parse_amount(match.group("max"))
    if low is not None and low < 100 and "hour" in text.lower():
        low, high = low * 2080, (high * 2080 if high else None)
    if low is not None and high is not None and high < low:
        low, high = high, low
    return low, high, currency


def parse_date(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        # Unix seconds/milliseconds or Excel serial
        try:
            if value > 1e12:
                value = value / 1000
            if value > 10_000_000_000:
                return None
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return parse_date(int(text))
    text = text.replace("Z", "+00:00")
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%m/%d/%Y", "%d %B %Y", "%B %d, %Y",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Country / mode / category heuristics
# ---------------------------------------------------------------------------

def detect_country(*values: str | None) -> tuple[str | None, str | None]:
    """Return (country_code, country_name) from free text. Empty means worldwide."""
    blob = fold_text(" ".join(v for v in values if v))
    if not blob:
        return None, None
    # Direct country names from the ISO table (English names + aliases first).
    for alias, code in sorted(COUNTRY_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias and re.search(rf"\b{re.escape(fold_text(alias))}\b", blob):
            return (code or None), (alias.title() if code else None)
    for code in COUNTRIES:
        from babel import Locale

        names = set()
        for lang in ("en", "fr", "ar"):
            try:
                name = Locale.parse(lang).territories.get(code.upper())
            except Exception:
                name = None
            if name:
                names.add(fold_text(name))
        for name in names:
            if name and re.search(rf"\b{re.escape(name)}\b", blob):
                return code, name.title()
    return None, None


_REMOTE_RE = re.compile(r"\b(remote|telecommute|work from home|télétravail|teletravail|عن بعد|عن بُعد)\b", re.I)
_HYBRID_RE = re.compile(r"\b(hybrid|hybride|هجين)\b", re.I)
_ONSITE_RE = re.compile(r"\b(on-?site|in-?office|sur site|في الموقع)\b", re.I)


def detect_work_mode(text: str | None, default: str | None = None) -> str | None:
    if not text:
        return default
    if _HYBRID_RE.search(text):
        return "hybrid"
    if _REMOTE_RE.search(text):
        return "remote"
    if _ONSITE_RE.search(text):
        return "onsite"
    return default


EMPLOYMENT_PATTERNS = [
    ("internship", r"\b(intern|internship|stage|stagiaire|تدريب|متدرب)\b"),
    ("apprenticeship", r"\b(apprentice|apprenticeship|alternance|تلمذة)\b"),
    ("part_time", r"\b(part[- ]time|temps partiel|دوام جزئي)\b"),
    ("temporary", r"\b(temporary|seasonal|saisonnier|temp\b|مؤقت|موسمي)\b"),
    ("contract", r"\b(contract|contractor|freelance|cdd|contrat|عقد)\b"),
    ("full_time", r"\b(full[- ]time|permanent|cdi|temps plein|دوام كامل)\b"),
]


def detect_employment_type(*values: str | None, default: str | None = None) -> str | None:
    blob = " ".join(v for v in values if v)
    for key, pattern in EMPLOYMENT_PATTERNS:
        if re.search(pattern, blob, re.I):
            return key
    return default


SENIORITY_PATTERNS = [
    ("executive", r"\b(chief|cto|ceo|cfo|coo|vp|vice president|head of|directeur general|مدير تنفيذي)\b"),
    ("lead", r"\b(lead|principal|staff|manager|responsable|chef d'equipe|قائد)\b"),
    ("senior", r"\b(senior|sr\.?|confirmé|confirme|خبير|أول)\b"),
    ("entry", r"\b(entry[- ]level|graduate|junior|intern|trainee|debutant|débutant|مبتدئ)\b"),
    ("mid", r"\b(mid[- ]level|intermediate|intermediaire|متوسط)\b"),
]


def detect_seniority(*values: str | None) -> str | None:
    blob = " ".join(v for v in values if v)
    for key, pattern in SENIORITY_PATTERNS:
        if re.search(pattern, blob, re.I):
            return key
    return None


CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "healthcare": ["nurse", "doctor", "physician", "surgeon", "dentist", "pharmac", "radiolog", "midwife", "clinical", "hospital", "infirmier", "médecin", "medecin", "طبيب", "ممرض", "تمريض", "صيدل"],
    "care": ["care worker", "caregiver", "care assistant", "nursing home", "home care", "support worker", "aide soignant", "aide-soignant", "auxiliaire", "رعاية", "مقدم رعاية"],
    "education": ["teacher", "professor", "lecturer", "tutor", "educator", "school", "kindergarten", "enseignant", "professeur", "formateur", "مدرس", "معلم", "أستاذ", "تعليم"],
    "hospitality": ["hotel", "restaurant", "chef", "cook", "waiter", "waitress", "barista", "housekeep", "reception", "tourism", "hôtel", "cuisinier", "serveur", "فندق", "طاهي", "نادل", "سياحة"],
    "construction": ["construction", "builder", "electrician", "plumber", "welder", "carpenter", "mason", "scaffold", "hvac", "mason", "maçon", "électricien", "plombier", "soudeur", "بناء", "كهربائي", "سباك", "لحام"],
    "agriculture": ["farm", "agricultur", "harvest", "horticultur", "livestock", "dairy", "picker", "agriculteur", "ouvrier agricole", "مزارع", "زراعة", "حصاد"],
    "logistics": ["driver", "logistic", "warehouse", "supply chain", "forklift", "delivery", "courier", "shipping", "chauffeur", "magasinier", "logistique", "سائق", "لوجستيات", "مستودع", "توصيل"],
    "manufacturing": ["manufactur", "factory", "production operator", "assembly", "machinist", "quality control", "usine", "ouvrier", "تصنيع", "مصنع", "إنتاج"],
    "engineering": ["engineer", "engineering", "mechanical", "electrical", "civil engineer", "structural", "ingénieur", "ingenieur", "مهندس", "هندسة"],
    "it": ["software", "developer", "programmer", "data scientist", "devops", "cyber", "cloud", "it support", "qa engineer", "développeur", "developpeur", "informatique", "مطور", "مبرمج", "بيانات", "أمن سيبراني"],
    "finance": ["accountant", "finance", "financial", "audit", "bank", "tax", "bookkeep", "comptable", "finance", "محاسب", "مالية", "تدقيق"],
    "legal": ["lawyer", "legal", "paralegal", "attorney", "solicitor", "jurist", "avocat", "juridique", "محامي", "قانون"],
    "science": ["scientist", "research", "laboratory", "lab technician", "biolog", "chemist", "physicist", "chercheur", "recherche", "عالم", "بحث", "مختبر"],
    "creative": ["designer", "graphic", "ux", "ui", "artist", "writer", "editor", "photograph", "video", "créatif", "graphiste", "مصمم", "فنان", "محرر"],
    "admin": ["administrative", "office manager", "secretary", "receptionist", "assistant", "data entry", "administration", "secrétaire", "إداري", "سكرتير", "مساعد"],
    "energy": ["energy", "solar", "wind", "oil", "gas", "power plant", "renewable", "électricité", "énergie", "طاقة", "نفط", "غاز", "متجددة"],
    "sales": ["sales", "business development", "account executive", "retail assistant", "store manager", "vente", "commercial", "مبيعات", "تطوير أعمال"],
    "marketing": ["marketing", "seo", "social media", "brand", "content", "communication", "marketing", "تسويق", "إعلام"],
    "support": ["customer support", "customer service", "helpdesk", "call center", "support agent", "service client", "دعم العملاء", "خدمة العملاء"],
    "hr": ["human resources", "recruit", "talent", "hr ", "people operations", "ressources humaines", "recrutement", "موارد بشرية", "توظيف"],
    "security": ["security guard", "security officer", "surveillance", "safety officer", "sécurité", "حارس", "أمن"],
    "public": ["public sector", "government", "civil service", "municipal", "secteur public", "gouvernement", "حكومي", "بلدية"],
    "social": ["social worker", "social care", "youth worker", "counsellor", "counselor", "travailleur social", "أخصائي اجتماعي", "إرشاد"],
    "automotive": ["automotive", "mechanic", "car ", "vehicle", "garage", "mécanicien", "mécanique", "سيارات", "ميكانيكي"],
    "aviation": ["aviation", "pilot", "cabin crew", "air traffic", "aircraft", "avion", "طيران", "طيار", "مضيف"],
    "retail": ["retail", "shop assistant", "cashier", "store", "supermarket", "commerce", "vente", "تجزئة", "بائع", "متجر"],
}


def detect_category(*values: str | None) -> str:
    blob = fold_text(" ".join(v for v in values if v))
    best, best_score = "other", 0
    for category, words in CATEGORY_KEYWORDS.items():
        score = sum(1 for w in words if fold_text(w) in blob)
        if score > best_score:
            best, best_score = category, score
    return best


def detect_language(text: str | None) -> str:
    if not text:
        return "en"
    sample = text[:1200]
    arabic = len(re.findall(r"[\u0600-\u06FF]", sample))
    if arabic > max(12, len(sample) * 0.08):
        return "ar"
    words = set(re.findall(r"[a-zà-ÿ]+", sample.lower()))
    french = {"le", "la", "les", "des", "du", "une", "nous", "vous", "pour", "avec", "dans", "sur", "est", "sont", "poste", "recherche", "contrat", "salaire"}
    english = {"the", "and", "with", "for", "you", "we", "are", "our", "role", "job", "team", "work", "experience", "salary"}
    fr_score = len(words & french)
    en_score = len(words & english)
    if fr_score > en_score * 1.3:
        return "fr"
    return "en"


# ---------------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------------

def flag_url(country_code: str | None) -> str:
    if country_code and len(country_code) == 2:
        path = STATIC_DIR / "flags" / f"{country_code.lower()}.svg"
        if path.exists():
            return f"/static/flags/{country_code.lower()}.svg"
    return ""


def region_icon(country_code: str | None) -> str:
    region = region_for(country_code)
    path = STATIC_DIR / "regions" / f"{region}.svg"
    if path.exists():
        return f"/static/regions/{region}.svg"
    return "/static/regions/worldwide.svg"


def logo_or_fallback(logo_path: str | None, country_code: str | None, logo_kind: str | None = None) -> str:
    if logo_path and logo_kind == "company":
        return logo_path
    if logo_path and logo_kind in {"country", "region"}:
        return logo_path
    if country_code:
        flag = flag_url(country_code)
        if flag:
            return flag
    return region_icon(country_code)


def is_safe_text(value: str) -> bool:
    return not re.search(r"<script|javascript:|onerror\s*=", value or "", re.I)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def human_file_size(num: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.1f} {unit}" if unit != "B" else f"{num} B"
        num /= 1024
    return f"{num:.1f} TB"


def category_of(listing) -> str:
    return listing.category if listing.category in CATEGORIES else "other"
