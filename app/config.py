"""Application configuration.

All secrets and tunables come from the environment (.env is loaded by
pydantic-settings). Nothing secret is ever sent to the browser.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
STATIC_DIR = BASE_DIR / "static"
I18N_DIR = DATA_DIR / "i18n"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    secret_key: str = "dev-only-change-me"
    database_url: str = f"sqlite:///{(DATA_DIR / 'eurojobs.db').as_posix()}"
    redis_url: str = ""

    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model_fast: str = "gemini-2.5-flash-lite"
    gemini_model_quality: str = "gemini-2.5-flash"
    gemini_free_tier: bool = True
    llm_rpm_fast: int = 10
    llm_rpd_fast: int = 200
    llm_rpm_quality: int = 5
    llm_rpd_quality: int = 50
    llm_user_daily_limit: int = 20
    llm_background_share: float = 0.2
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    jooble_api_key: str = ""
    rapidapi_key: str = ""
    reed_api_key: str = ""
    reliefweb_appname: str = ""
    reliefweb_countries: str = ""
    logo_service_token: str = ""
    logo_service_url: str = "https://img.logo.dev/{domain}?token={token}&size=128"

    ingest_interval_minutes: int = 20
    link_check_interval_hours: int = 6
    logo_cache_dir: str = str(STATIC_DIR / "logos")
    logo_refresh_days: int = 30

    default_language: str = "en"
    supported_languages: str = "ar,fr,en"
    enable_scheduler: bool = True
    admin_emails: str = ""

    max_upload_mb: int = 5

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]

    @property
    def languages(self) -> list[str]:
        langs = [x.strip() for x in self.supported_languages.split(",") if x.strip()]
        return langs or ["en"]

    @property
    def ai_enabled(self) -> bool:
        return bool(self.gemini_api_key) or self.llm_provider != "gemini"

    @property
    def logo_dir(self) -> Path:
        p = Path(self.logo_cache_dir)
        if not p.is_absolute():
            p = BASE_DIR / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def reliefweb_country_list(self) -> list[str]:
        return [c.strip().upper() for c in self.reliefweb_countries.split(",") if c.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

# Ensure runtime folders exist.
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "logos").mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "flags").mkdir(parents=True, exist_ok=True)
(DATA_DIR / "registers").mkdir(parents=True, exist_ok=True)
