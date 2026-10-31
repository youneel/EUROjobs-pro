"""Source registry and health helpers."""
from __future__ import annotations

from app.config import settings
from app.sources.adzuna import AdzunaSource
from app.sources.arbeitnow import ArbeitnowSource
from app.sources.ats import ats_sources
from app.sources.himalayas import HimalayasSource
from app.sources.jobicy import JobicySource
from app.sources.jooble import JoobleSource
from app.sources.reed import ReedSource
from app.sources.reliefweb import ReliefWebSource
from app.sources.remoteok import RemoteOKSource
from app.sources.remotive import RemotiveSource
from app.sources.themuse import TheMuseSource

KEYLESS = [ArbeitnowSource, JobicySource, RemotiveSource, RemoteOKSource, HimalayasSource, TheMuseSource]
KEYED = [AdzunaSource, JoobleSource, ReedSource, ReliefWebSource]


def all_sources() -> list:
    sources: list = []
    for cls in KEYLESS + KEYED:
        source = cls()
        if source.enabled:
            sources.append(source)
    sources.extend(ats_sources())
    return sources


def live_sources() -> list:
    """Keyless + keyed sources that support a keyword query, fastest first."""
    return [s for s in all_sources() if type(s).__name__ in {
        "RemotiveSource", "JobicySource", "HimalayasSource", "AdzunaSource",
        "JoobleSource", "ReedSource", "ReliefWebSource", "TheMuseSource",
    }]


def source_status() -> dict:
    return {
        "configured": {
            "adzuna": bool(settings.adzuna_app_id and settings.adzuna_app_key),
            "jooble": bool(settings.jooble_api_key),
            "reed": bool(settings.reed_api_key),
            "reliefweb": bool(settings.reliefweb_appname),
            "gemini": bool(settings.gemini_api_key),
        },
        "keyless": [cls().name for cls in KEYLESS],
        "ats_boards": len(ats_sources()),
        "llm_provider": settings.llm_provider,
        "free_tier": settings.gemini_free_tier,
    }
