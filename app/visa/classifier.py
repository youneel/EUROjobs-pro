"""Visa-sponsorship verification: rules first, AI last.

Jobs need Tier 1 (official register for the job's country) or Tier 2 (explicit
sponsorship language in the posting). Volunteers need Level 1 (verified
programme with documented visa support) or Level 2 (explicit support language).

Negative phrases always win. The classifier never claims sponsorship is
guaranteed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from app.utils import excerpt, fold_text
from app.visa.programs import match_program
from app.visa.registers import get_registers

# ---------------------------------------------------------------------------
# Phrase rules (jobs)
# ---------------------------------------------------------------------------

JOB_POSITIVE = [
    # English
    r"visa sponsorship", r"sponsorship (?:is )?available", r"we (?:will |can )?sponsor",
    r"sponsor(?:ing)? (?:a |your )?(?:work )?visa", r"work visa (?:provided|supported)",
    r"work permit (?:provided|supported|sponsored)", r"certificate of sponsorship",
    r"skilled worker visa", r"tier 2 visa", r"h-?1b", r"h-?2a", r"h-?2b",
    r"eu blue card", r"blue card", r"relocation (?:package|support|assistance|bonus)",
    r"we (?:will |can )?(?:help|assist) (?:you )?with (?:your )?visa",
    r"right to work support", r"immigration support", r"visa support",
    # French
    r"parrainage (?:de |du )?visa", r"sponsoring (?:de |du )?visa",
    r"aide (?:à |a )?l(?:'|’)obtention du visa", r"prise en charge du visa",
    r"visa sponsoris[ée]", r"permis de travail (?:fourni|pris en charge)",
    r"carte bleue europ[ée]enne", r"accompagnement (?:visa|administratif)",
    r"aide à la relocalisation", r"relocation",
    # Arabic
    r"كفالة (?:ال)?تأشيرة", r"رعاية (?:ال)?تأشيرة", r"دعم (?:ال)?تأشيرة",
    r"تأشيرة عمل", r"توفير تأشيرة", r"تكفل (?:الشركة|المؤسسة)",
    r"بطاقة (?:الاتحاد الأوروبي )?الزرقاء", r"مساعدة في التأشيرة",
    # German
    r"visumsponsoring", r"visa-?unterst[üu]tzung", r"relocation-?unterst[üu]tzung",
    r"arbeitsvisum", r"blaue karte",
    # Spanish / Portuguese / Italian / Dutch
    r"patrocinio de visa", r"apoyo con (?:el )?visado", r"reubicaci[óo]n",
    r"patroc[íi]nio de visto", r"apoio com (?:o )?visto", r"patrocinio del visto",
    r"visumsponsoring", r"werkvisum",
]

JOB_NEGATIVE = [
    r"no (?:visa )?sponsorship", r"not (?:able|in a position) to sponsor",
    r"(?:unable|cannot|can(?:'|’)t|will not|do not|don(?:'|’)t) (?:to )?sponsor",
    r"sponsorship (?:is )?not (?:available|offered|provided)",
    r"without (?:visa )?sponsorship", r"no work permit",
    r"must (?:already )?(?:have|possess) the right to work",
    r"must be (?:authori[sz]ed|eligible) to work", r"must already (?:be )?(?:authori[sz]ed|eligible|resident)",
    r"right to work (?:is )?required", r"no visa support", r"visa (?:is )?not (?:provided|supported)",
    # French
    r"pas de (?:sponsoring|parrainage)", r"aucun (?:sponsoring|parrainage)",
    r"(?:nous )?ne sponsorisons pas", r"sans (?:sponsoring|parrainage)",
    r"ne (?:prenons|prend) pas en charge (?:le |la )?visa",
    r"visa (?:à |a )votre charge", r"devez (?:déjà|deja) (?:être|etre) autoris[ée]",
    r"droit de travailler (?:exig[ée]|requis)",
    # Arabic
    r"لا (?:نوفر|نقدم|ندعم) (?:(?:كفالة|دعم\s+)?(?:ال)?تأشيرة|كفالة\s+(?:ال)?تأشيرة)",
    r"بدون (?:كفالة|دعم تأشيرة)", r"لا كفالة", r"لا يوجد دعم للتأشيرة",
    r"يجب أن (?:تكون|تمتلك) (?:حق العمل|إقامة|تصريح عمل)",
    r"على المتقدم ترتيب تأشيرته",
    # German
    r"keine visum-?unterst[üu]tzung", r"kein visumsponsoring", r"wir sponsern nicht",
    r"arbeitserlaubnis (?:erforderlich|vorausgesetzt)",
    # Spanish / Portuguese
    r"sin patrocinio", r"no patrocinamos", r"sem patroc[íi]nio", r"n[ãa]o patrocinamos",
]

VOLUNTEER_POSITIVE = [
    r"visa support", r"visa assistance", r"help (?:you )?with (?:your )?visa",
    r"invitation letter", r"letter of invitation", r"visa sponsorship",
    r"volunteer visa", r"visa guidance", r"visa application support",
    r"supports? (?:the |your )?visa", r"visa (?:is )?(?:arranged|provided|sponsored)",
    # French
    r"lettre d(?:'|’)invitation", r"accompagnement (?:visa|administratif)",
    r"aide (?:pour|à |a )?(?:le |la )?visa", r"prise en charge du visa",
    r"soutien (?:visa|administratif)", r"visa (?:fourni|pris en charge)",
    # Arabic
    r"خطاب دعوة", r"دعم (?:ال)?تأشيرة", r"كفالة (?:ال)?تأشيرة",
    r"مساعدة في (?:ال)?تأشيرة", r"تأشيرة (?:العمل|التطوع)",
    # German / Spanish / Portuguese
    r"visum-?unterst[üu]tzung", r"einladungsschreiben",
    r"apoyo con (?:el )?visado", r"carta de invitaci[óo]n",
    r"apoio com (?:o )?visto", r"carta convite",
]

VOLUNTEER_NEGATIVE = [
    r"volunteers? (?:must |should |need to )?(?:arrange|obtain|secure) (?:their |your )?own visa",
    r"own visa (?:required|responsibility)", r"no visa (?:support|assistance)",
    r"visa (?:support|assistance) (?:is )?not (?:provided|available)",
    r"must (?:already )?(?:have|possess) the right to (?:work|volunteer)",
    r"no invitation letter", r"cannot provide (?:a )?visa",
    # French
    r"les b[ée]n[ée]voles doivent (?:organiser|obtenir) (?:leur|eux-m[êe]mes)",
    r"pas de prise en charge du visa", r"visa (?:à |a )votre charge",
    r"pas de lettre d(?:'|’)invitation", r"sans (?:soutien|accompagnement) visa",
    # Arabic
    r"يتولى المتطوع(?:ون)? ترتيب تأشيرتهم", r"لا نوفر دعم (?:ال)?تأشيرة",
    r"لا (?:نقدم|ندعم) (?:ال)?تأشيرة", r"ليست لدينا كفالة",
    # German / Spanish
    r"keine visum-?unterst[üu]tzung", r"visum selbst (?:beantragen|organisieren)",
    r"sin apoyo (?:con )?(?:el )?visado", r"los voluntarios deben organizar",
]

VOLUNTEER_HINTS = re.compile(
    r"\b(volunteer(?:ing|s)?|voluntary|b[ée]n[ée]vol(?:at|e)|volontariat|"
    r"تطو(?:ع|ّع)|متطوع(?:ون|ين)?|unpaid (?:role|position|placement))\b",
    re.I,
)
PAID_INTERNSHIP = re.compile(r"\b(paid|r[ée]mun[ée]r[ée]|مدفوع)\b.{0,30}\b(intern|stage|تدريب)\b", re.I)

FEE_PATTERNS = [
    r"program(?:me)? fee", r"participation fee", r"placement fee", r"registration fee",
    r"administration fee", r"deposit (?:of|required)", r"you will (?:need to )?pay",
    r"frais de participation", r"frais d(?:'|’)inscription", r"frais de placement",
    r"frais administratifs", r"vous devrez payer",
    r"رسوم المشاركة", r"رسوم التسجيل", r"رسوم التوظيف", r"رسوم إدارية",
    r"عليك (?:أن )?تدفع", r"تبلغ رسوم",
]
SCAM_PATTERNS = [
    r"western union", r"moneygram", r"money transfer", r"bank transfer to (?:an )?individual",
    r"contact (?:us )?(?:only )?on whatsapp", r"send (?:us )?(?:a )?(?:payment|money|fee)",
    r"visa fee", r"pay (?:a |the )?visa fee", r"urgent payment",
    r"paiement par western union", r"frais de visa", r"envoyez (?:l'argent|le paiement)",
    r"رسوم التأشيرة", r"حوالة مالية", r"ادفع رسوم التأشيرة",
]

_POS_COMPILED = [re.compile(p, re.I) for p in JOB_POSITIVE]
_NEG_COMPILED = [re.compile(p, re.I) for p in JOB_NEGATIVE]
_VPOS_COMPILED = [re.compile(p, re.I) for p in VOLUNTEER_POSITIVE]
_VNEG_COMPILED = [re.compile(p, re.I) for p in VOLUNTEER_NEGATIVE]
_FEE_COMPILED = [re.compile(p, re.I) for p in FEE_PATTERNS]
_SCAM_COMPILED = [re.compile(p, re.I) for p in SCAM_PATTERNS]


@dataclass
class VisaResult:
    tier: int
    evidence: str
    visa_type_hint: str | None = None
    reason: str = ""
    needs_ai: bool = False
    negative: bool = False


def _first_match(patterns: list[re.Pattern[str]], text: str) -> re.Match[str] | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match
    return None


def _snippet(text: str, match: re.Match[str], width: int = 150) -> str:
    start = max(0, match.start() - width)
    end = min(len(text), match.end() + width)
    return excerpt(text[start:end], width * 2 + 40)


def _visa_hint(text: str) -> str | None:
    low = text.lower()
    if "h-1b" in low or "h1b" in low:
        return "US H-1B"
    if "h-2a" in low:
        return "US H-2A"
    if "h-2b" in low:
        return "US H-2B"
    if "blue card" in low or "carte bleue" in low or "بطاقة" in low:
        return "EU Blue Card"
    if "skilled worker" in low or "tier 2" in low:
        return "UK Skilled Worker"
    if "seasonal" in low or "saisonnier" in low or "موسمي" in low:
        return "Seasonal work"
    if "volunteer" in low or "bénévol" in low or "تطوع" in low:
        return "Volunteer route"
    return None


def is_volunteer_posting(title: str | None, description: str | None, employment_type: str | None = None) -> bool:
    blob = " ".join(x for x in (title, description) if x)
    if PAID_INTERNSHIP.search(blob):
        return False
    if employment_type in {"internship", "apprenticeship"} and not VOLUNTEER_HINTS.search(title or ""):
        return False
    return bool(VOLUNTEER_HINTS.search(blob))


def detect_fee(text: str | None) -> tuple[bool, float | None, str | None]:
    if not text:
        return False, None, None
    match = _first_match(_FEE_COMPILED, text)
    if not match:
        return False, None, None
    window = text[max(0, match.start() - 60): match.end() + 120]
    amount = re.search(r"(?:USD|EUR|GBP|CAD|AUD|\$|€|£)\s?(\d[\d,.]*)", window, re.I)
    value = None
    if amount:
        try:
            value = float(amount.group(1).replace(",", ""))
        except ValueError:
            value = None
    currency = None
    symbol = re.search(r"(USD|EUR|GBP|CAD|AUD|\$|€|£)", window, re.I)
    if symbol:
        currency = {"$": "USD", "€": "EUR", "£": "GBP"}.get(symbol.group(1), symbol.group(1).upper())
    return True, value, currency


def detect_scam(text: str | None) -> list[str]:
    if not text:
        return []
    return [pattern.pattern for pattern in _SCAM_COMPILED if pattern.search(text)]


def classify_job(
    *,
    title: str,
    company: str,
    description: str | None,
    country_code: str | None,
    source_flag: bool | None = None,
    source_name: str = "",
) -> VisaResult:
    text = f"{title}\n{description or ''}"
    negative = _first_match(_NEG_COMPILED, text)
    if negative:
        return VisaResult(
            tier=0,
            evidence=_snippet(text, negative),
            reason="negative phrase overrides positive signals",
            negative=True,
        )
    if source_flag:
        return VisaResult(
            tier=2,
            evidence=f"Source flag from {source_name or 'the provider'} marks visa sponsorship.",
            visa_type_hint=_visa_hint(text),
            reason="explicit source flag",
        )
    register = get_registers().match(company, country_code)
    if register:
        return VisaResult(
            tier=1,
            evidence=f"{register.source} · route: {register.route}. A licence is not a guarantee for this role.",
            visa_type_hint=_visa_hint(text) or register.route,
            reason="official sponsor register for the job's country",
        )
    positive = _first_match(_POS_COMPILED, text)
    if positive:
        return VisaResult(
            tier=2,
            evidence=_snippet(text, positive),
            visa_type_hint=_visa_hint(text),
            reason="explicit sponsorship language",
        )
    ambiguous = bool(re.search(r"\b(visa|immigration|work permit|authori[sz]ation|relocation)\b", text, re.I))
    return VisaResult(tier=0, evidence="", reason="no sponsorship evidence", needs_ai=ambiguous)


def classify_volunteer(
    *,
    title: str,
    organisation: str,
    description: str | None,
    country_code: str | None,
    source_flag: bool | None = None,
) -> VisaResult:
    text = f"{title}\n{description or ''}"
    negative = _first_match(_VNEG_COMPILED, text)
    if negative:
        return VisaResult(
            tier=0,
            evidence=_snippet(text, negative),
            reason="negative volunteer visa phrase",
            negative=True,
        )
    programme = match_program(organisation, country_code)
    if programme:
        return VisaResult(
            tier=1,
            evidence=programme.evidence,
            visa_type_hint="Volunteer / exchange route",
            reason="verified programme with documented visa support",
        )
    if source_flag:
        return VisaResult(
            tier=2,
            evidence="Source marks visa support for this volunteer placement.",
            visa_type_hint="Volunteer route",
            reason="explicit source flag",
        )
    positive = _first_match(_VPOS_COMPILED, text)
    if positive:
        return VisaResult(
            tier=2,
            evidence=_snippet(text, positive),
            visa_type_hint="Volunteer route",
            reason="explicit volunteer visa-support language",
        )
    ambiguous = bool(re.search(r"\b(visa|invitation|immigration|permit)\b", text, re.I))
    return VisaResult(tier=0, evidence="", reason="no volunteer visa support", needs_ai=ambiguous)


def classify_listing(listing, source_flag: bool | None = None) -> VisaResult:
    if listing.listing_type == "volunteer":
        return classify_volunteer(
            title=listing.title,
            organisation=listing.company,
            description=listing.description_text,
            country_code=listing.country_code,
            source_flag=source_flag,
        )
    return classify_job(
        title=listing.title,
        company=listing.company,
        description=listing.description_text,
        country_code=listing.country_code,
        source_flag=source_flag,
        source_name=listing.source_name,
    )


def badge_key(listing_type: str, tier: int) -> str:
    if listing_type == "volunteer":
        return "volunteer.support_confirmed" if tier == 1 else "volunteer.support_mentioned"
    return "visa.verified_sponsor" if tier == 1 else "visa.sponsorship_mentioned"


def badge_explain_key(listing_type: str, tier: int) -> str:
    if listing_type == "volunteer":
        return "volunteer.legal"
    return "visa.verified_explain" if tier == 1 else "visa.mentioned_explain"


def apply_ai_decision(listing, supported: bool, confidence: float, evidence: str = "") -> None:
    """Persist an ambiguous-case AI decision (background quota only)."""
    listing.visa_checked_at = datetime.now(timezone.utc)
    if supported:
        listing.visa_tier = min(listing.visa_tier or 2, 2)
        listing.visa_evidence = (
            f"AI-assisted classification ({confidence:.0%} confidence). {evidence}".strip()
        )
    else:
        listing.visa_tier = 0
        listing.visa_evidence = "AI review found no sponsorship evidence."
