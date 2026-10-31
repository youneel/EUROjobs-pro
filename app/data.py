"""Static reference data: countries, regions, categories and search synonyms."""
from __future__ import annotations

# ISO2 -> (region key, currency). Regions drive flag/region fallbacks.
COUNTRIES: dict[str, tuple[str, str]] = {
    # Europe / EU
    "at": ("eu", "EUR"), "be": ("eu", "EUR"), "bg": ("eu", "BGN"), "hr": ("eu", "EUR"),
    "cy": ("eu", "EUR"), "cz": ("eu", "CZK"), "dk": ("eu", "DKK"), "ee": ("eu", "EUR"),
    "fi": ("eu", "EUR"), "fr": ("eu", "EUR"), "de": ("eu", "EUR"), "gr": ("eu", "EUR"),
    "hu": ("eu", "HUF"), "ie": ("eu", "EUR"), "it": ("eu", "EUR"), "lv": ("eu", "EUR"),
    "lt": ("eu", "EUR"), "lu": ("eu", "EUR"), "mt": ("eu", "EUR"), "nl": ("eu", "EUR"),
    "pl": ("eu", "PLN"), "pt": ("eu", "EUR"), "ro": ("eu", "RON"), "sk": ("eu", "EUR"),
    "si": ("eu", "EUR"), "es": ("eu", "EUR"), "se": ("eu", "SEK"),
    # Rest of Europe
    "gb": ("europe", "GBP"), "ch": ("europe", "CHF"), "no": ("europe", "NOK"),
    "is": ("europe", "ISK"), "rs": ("europe", "RSD"), "ba": ("europe", "BAM"),
    "mk": ("europe", "MKD"), "al": ("europe", "ALL"), "me": ("europe", "EUR"),
    "md": ("europe", "MDL"), "ua": ("europe", "UAH"), "by": ("europe", "BYN"),
    "ru": ("europe", "RUB"), "tr": ("europe", "TRY"),
    # North America
    "us": ("north_america", "USD"), "ca": ("north_america", "CAD"),
    # Latin America
    "mx": ("latam", "MXN"), "br": ("latam", "BRL"), "ar": ("latam", "ARS"),
    "cl": ("latam", "CLP"), "co": ("latam", "COP"), "pe": ("latam", "PEN"),
    "ec": ("latam", "USD"), "uy": ("latam", "UYU"), "py": ("latam", "PYG"),
    "bo": ("latam", "BOB"), "ve": ("latam", "VES"), "cr": ("latam", "CRC"),
    "pa": ("latam", "PAB"), "gt": ("latam", "GTQ"), "hn": ("latam", "HNL"),
    "sv": ("latam", "USD"), "ni": ("latam", "NIO"), "do": ("latam", "DOP"),
    "cu": ("latam", "CUP"), "jm": ("latam", "JMD"), "tt": ("latam", "TTD"),
    "bs": ("latam", "BSD"), "bb": ("latam", "BBD"), "gd": ("latam", "XCD"),
    "lc": ("latam", "XCD"), "vc": ("latam", "XCD"), "ag": ("latam", "XCD"),
    "dm": ("latam", "XCD"), "kn": ("latam", "XCD"), "ht": ("latam", "HTG"),
    "pr": ("latam", "USD"),
    # Middle East & North Africa
    "ma": ("mena", "MAD"), "dz": ("mena", "DZD"), "tn": ("mena", "TND"),
    "ly": ("mena", "LYD"), "eg": ("mena", "EGP"), "sa": ("mena", "SAR"),
    "ae": ("mena", "AED"), "qa": ("mena", "QAR"), "kw": ("mena", "KWD"),
    "bh": ("mena", "BHD"), "om": ("mena", "OMR"), "jo": ("mena", "JOD"),
    "lb": ("mena", "LBP"), "sy": ("mena", "SYP"), "iq": ("mena", "IQD"),
    "ir": ("mena", "IRR"), "il": ("mena", "ILS"), "ps": ("mena", "ILS"),
    "ye": ("mena", "YER"),
    # Africa
    "ng": ("africa", "NGN"), "gh": ("africa", "GHS"), "ke": ("africa", "KES"),
    "za": ("africa", "ZAR"), "et": ("africa", "ETB"), "ug": ("africa", "UGX"),
    "tz": ("africa", "TZS"), "rw": ("africa", "RWF"), "sn": ("africa", "XOF"),
    "ci": ("africa", "XOF"), "cm": ("africa", "XAF"), "zm": ("africa", "ZMW"),
    "zw": ("africa", "ZWL"), "bw": ("africa", "BWP"), "na": ("africa", "NAD"),
    "mz": ("africa", "MZN"), "ao": ("africa", "AOA"), "cd": ("africa", "CDF"),
    "ml": ("africa", "XOF"), "bf": ("africa", "XOF"), "ne": ("africa", "XOF"),
    "td": ("africa", "XAF"), "sd": ("africa", "SDG"), "ss": ("africa", "SSP"),
    "so": ("africa", "SOS"), "er": ("africa", "ERN"), "dj": ("africa", "DJF"),
    "mg": ("africa", "MGA"), "mu": ("africa", "MUR"), "sc": ("africa", "SCR"),
    "cv": ("africa", "CVE"), "gm": ("africa", "GMD"), "gn": ("africa", "GNF"),
    "gw": ("africa", "XOF"), "sl": ("africa", "SLE"), "lr": ("africa", "LRD"),
    "tg": ("africa", "XOF"), "bj": ("africa", "XOF"), "mr": ("africa", "MRU"),
    # Asia-Pacific
    "cn": ("asia_pacific", "CNY"), "jp": ("asia_pacific", "JPY"),
    "kr": ("asia_pacific", "KRW"), "in": ("asia_pacific", "INR"),
    "pk": ("asia_pacific", "PKR"), "bd": ("asia_pacific", "BDT"),
    "lk": ("asia_pacific", "LKR"), "np": ("asia_pacific", "NPR"),
    "bt": ("asia_pacific", "BTN"), "mm": ("asia_pacific", "MMK"),
    "th": ("asia_pacific", "THB"), "vn": ("asia_pacific", "VND"),
    "kh": ("asia_pacific", "KHR"), "la": ("asia_pacific", "LAK"),
    "my": ("asia_pacific", "MYR"), "sg": ("asia_pacific", "SGD"),
    "id": ("asia_pacific", "IDR"), "ph": ("asia_pacific", "PHP"),
    "au": ("asia_pacific", "AUD"), "nz": ("asia_pacific", "NZD"),
    "fj": ("asia_pacific", "FJD"), "pg": ("asia_pacific", "PGK"),
    "ws": ("asia_pacific", "WST"), "to": ("asia_pacific", "TOP"),
    "vu": ("asia_pacific", "VUV"), "sb": ("asia_pacific", "SBD"),
    "ki": ("asia_pacific", "AUD"), "tv": ("asia_pacific", "AUD"),
    "nr": ("asia_pacific", "AUD"), "fm": ("asia_pacific", "USD"),
    "mh": ("asia_pacific", "USD"), "pw": ("asia_pacific", "USD"),
    "bn": ("asia_pacific", "BND"), "tl": ("asia_pacific", "USD"),
    "mn": ("asia_pacific", "MNT"), "kz": ("asia_pacific", "KZT"),
    "uz": ("asia_pacific", "UZS"), "kg": ("asia_pacific", "KGS"),
    "tj": ("asia_pacific", "TJS"), "tm": ("asia_pacific", "TMT"),
    "az": ("asia_pacific", "AZN"), "ge": ("asia_pacific", "GEL"),
    "am": ("asia_pacific", "AMD"),
}

REGIONS = [
    "eu",
    "europe",
    "north_america",
    "latam",
    "mena",
    "africa",
    "asia_pacific",
    "worldwide",
]

# Country name aliases used when a source only gives a name.
COUNTRY_ALIASES: dict[str, str] = {
    "uk": "gb", "united kingdom": "gb", "great britain": "gb", "england": "gb",
    "usa": "us", "united states": "us", "united states of america": "us",
    "u.s.": "us", "u.s.a.": "us", "america": "us",
    "uae": "ae", "united arab emirates": "ae",
    "holland": "nl", "netherlands": "nl", "the netherlands": "nl",
    "deutschland": "de", "germany": "de",
    "espana": "es", "españa": "es", "spain": "es",
    "francia": "fr", "france": "fr",
    "italia": "it", "italy": "it",
    "brasil": "br", "brazil": "br",
    "turkiye": "tr", "türkiye": "tr", "turkey": "tr",
    "czechia": "cz", "czech republic": "cz",
    "south korea": "kr", "korea": "kr", "republic of korea": "kr",
    "russia": "ru", "russian federation": "ru",
    "vietnam": "vn", "viet nam": "vn",
    "ivory coast": "ci", "côte d'ivoire": "ci",
    "congo": "cd", "drc": "cd",
    "remote": "", "worldwide": "", "anywhere": "", "global": "",
}

# Broad categories (all sectors). Labels live in the i18n catalogues.
CATEGORIES = [
    "healthcare", "care", "education", "hospitality", "construction", "agriculture",
    "logistics", "manufacturing", "engineering", "it", "finance", "legal", "science",
    "creative", "admin", "energy", "sales", "marketing", "support", "hr", "security",
    "public", "social", "automotive", "aviation", "retail", "other",
]

CAUSE_AREAS = [
    "education", "environment", "health", "humanitarian", "animals", "community",
    "arts", "sports", "technology", "other",
]

ORG_TYPES = ["ngo", "un", "government", "charity", "school", "other"]

COUNTRY_STYLES = ["us", "uk", "de", "fr", "ar", "international"]

# Multilingual synonym groups. Every term maps to a canonical concept; a query
# containing any variant is expanded to all variants in the group.
SYNONYM_GROUPS: list[list[str]] = [
    ["nurse", "nursing", "infirmier", "infirmiere", "infirmière", "ممرض", "ممرضة", "تمريض"],
    ["doctor", "physician", "medecin", "médecin", "طبيب", "طبيبة"],
    ["caregiver", "care worker", "care assistant", "aide soignant", "aide-soignant", "مقدم رعاية", "رعاية"],
    ["teacher", "professor", "enseignant", "professeur", "مدرس", "معلم", "أستاذ"],
    ["engineer", "ingenieur", "ingénieur", "مهندس", "مهندسة"],
    ["developer", "software engineer", "programmer", "developpeur", "développeur", "مطور", "مبرمج"],
    ["data scientist", "data analyst", "analyste de donnees", "analyste de données", "عالم بيانات", "محلل بيانات"],
    ["accountant", "comptable", "محاسب", "محاسبة"],
    ["driver", "chauffeur", "سائق"],
    ["chef", "cook", "cuisinier", "طباخ", "طاهي"],
    ["waiter", "server", "serveur", "نادل", "نادلة"],
    ["receptionist", "receptionniste", "réceptionniste", "موظف استقبال"],
    ["cleaner", "housekeeper", "agent d'entretien", "femme de chambre", "عامل نظافة"],
    ["builder", "construction worker", "macon", "maçon", "عامل بناء"],
    ["electrician", "electricien", "électricien", "كهربائي"],
    ["plumber", "plombier", "سباك"],
    ["welder", "soudeur", "لحام"],
    ["farmer", "agricultural worker", "agriculteur", "ouvrier agricole", "مزارع", "عامل زراعي"],
    ["warehouse", "logistics", "magasinier", "logistique", "مستودع", "لوجستيات"],
    ["security guard", "agent de securite", "agent de sécurité", "حارس أمن"],
    ["teacher assistant", "assistant pedagogique", "مساعد تعليمي"],
    ["social worker", "travailleur social", "أخصائي اجتماعي"],
    ["translator", "traducteur", "مترجم"],
    ["designer", "graphiste", "مصمم"],
    ["manager", "responsable", "مدير"],
    ["internship", "stage", "تدريب"],
    ["volunteer", "benevolat", "bénévolat", "volontariat", "تطوع", "تطوّع", "متطوع"],
    ["visa sponsorship", "sponsorship", "parrainage", "كفالة"],
]

_SYNONYM_INDEX: dict[str, set[str]] = {}
for group in SYNONYM_GROUPS:
    for term in group:
        key = term.casefold().strip()
        _SYNONYM_INDEX.setdefault(key, set()).update(g.casefold().strip() for g in group)


def synonyms_for(term: str) -> set[str]:
    return _SYNONYM_INDEX.get(term.casefold().strip(), set())


REGION_ICON = {
    "eu": "eu",
    "europe": "europe",
    "north_america": "north-america",
    "latam": "latam",
    "mena": "mena",
    "africa": "africa",
    "asia_pacific": "asia-pacific",
    "worldwide": "world",
}


def region_for(country_code: str | None) -> str:
    if not country_code:
        return "worldwide"
    return COUNTRIES.get(country_code.lower(), ("worldwide", "USD"))[0]


def currency_for(country_code: str | None) -> str:
    if not country_code:
        return "USD"
    return COUNTRIES.get(country_code.lower(), ("worldwide", "USD"))[1]
