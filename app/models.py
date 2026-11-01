"""SQLAlchemy models.

The design keeps jobs and volunteers in one table (``listing_type`` is a hard
partition, never mixed in queries) with a one-to-one volunteer details table.
It is deliberately PostgreSQL-ready: only portable column types are used.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_public_id() -> str:
    return uuid.uuid4().hex[:14]


class Listing(Base):
    __tablename__ = "listing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(24), unique=True, index=True, default=new_public_id)
    listing_type: Mapped[str] = mapped_column(String(16), default="job", index=True)

    title: Mapped[str] = mapped_column(String(500))
    company: Mapped[str] = mapped_column(String(300), index=True)
    company_url: Mapped[str | None] = mapped_column(String(1000))
    company_domain: Mapped[str | None] = mapped_column(String(255), index=True)
    company_logo_url: Mapped[str | None] = mapped_column(String(1000))
    logo_path: Mapped[str | None] = mapped_column(String(500))
    logo_kind: Mapped[str | None] = mapped_column(String(16))  # company/country/region

    description_html: Mapped[str | None] = mapped_column(Text)
    description_text: Mapped[str | None] = mapped_column(Text)

    country: Mapped[str | None] = mapped_column(String(120), index=True)
    country_code: Mapped[str | None] = mapped_column(String(2), index=True)
    city: Mapped[str | None] = mapped_column(String(160))
    region: Mapped[str | None] = mapped_column(String(80))
    work_mode: Mapped[str | None] = mapped_column(String(16))  # remote/hybrid/onsite
    employment_type: Mapped[str | None] = mapped_column(String(40))
    category: Mapped[str | None] = mapped_column(String(80), index=True)
    seniority: Mapped[str | None] = mapped_column(String(40))
    salary_min: Mapped[float | None] = mapped_column(Float)
    salary_max: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(8))
    language: Mapped[str | None] = mapped_column(String(8), default="en")

    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    apply_url_original: Mapped[str | None] = mapped_column(String(1500))
    apply_url_final: Mapped[str | None] = mapped_column(String(1500))

    source_name: Mapped[str] = mapped_column(String(60), index=True)
    source_job_id: Mapped[str | None] = mapped_column(String(200))

    visa_tier: Mapped[int] = mapped_column(Integer, default=0, index=True)  # 0 rejected
    visa_evidence: Mapped[str | None] = mapped_column(Text)
    visa_type_hint: Mapped[str | None] = mapped_column(String(80))
    visa_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    dedupe_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    url_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    search_text: Mapped[str | None] = mapped_column(Text)
    extras: Mapped[dict | None] = mapped_column(JSON, default=dict)

    volunteer: Mapped["VolunteerDetails | None"] = relationship(
        back_populates="listing", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_listing_type_posted", "listing_type", "posted_at"),
        Index("ix_listing_type_country", "listing_type", "country_code"),
        Index("ix_listing_type_tier", "listing_type", "visa_tier"),
    )


class VolunteerDetails(Base):
    __tablename__ = "volunteer_details"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listing.id", ondelete="CASCADE"), unique=True, index=True
    )
    duration: Mapped[str | None] = mapped_column(String(120))
    start_date: Mapped[date | None] = mapped_column(Date)
    application_deadline: Mapped[date | None] = mapped_column(Date)
    hours_per_week: Mapped[str | None] = mapped_column(String(60))
    cause_area: Mapped[str | None] = mapped_column(String(80), index=True)
    org_type: Mapped[str | None] = mapped_column(String(40))
    skills_required: Mapped[str | None] = mapped_column(Text)
    languages_required: Mapped[str | None] = mapped_column(String(300))
    min_age: Mapped[int | None] = mapped_column(Integer)
    remote_volunteering: Mapped[bool] = mapped_column(Boolean, default=False)
    accommodation_provided: Mapped[bool | None] = mapped_column(Boolean)
    meals_provided: Mapped[bool | None] = mapped_column(Boolean)
    stipend: Mapped[float | None] = mapped_column(Float)
    stipend_currency: Mapped[str | None] = mapped_column(String(8))
    travel_covered: Mapped[bool | None] = mapped_column(Boolean)
    insurance_provided: Mapped[bool | None] = mapped_column(Boolean)
    fee_required: Mapped[bool] = mapped_column(Boolean, default=False)
    fee_amount: Mapped[float | None] = mapped_column(Float)
    fee_currency: Mapped[str | None] = mapped_column(String(8))
    visa_support_type: Mapped[str | None] = mapped_column(String(80))
    programme_name: Mapped[str | None] = mapped_column(String(300))
    scam_flags: Mapped[list | None] = mapped_column(JSON, default=list)

    listing: Mapped[Listing] = relationship(back_populates="volunteer")


class CompanyLogo(Base):
    __tablename__ = "company_logo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    company: Mapped[str] = mapped_column(String(300))
    domain: Mapped[str | None] = mapped_column(String(255))
    source_logo_url: Mapped[str | None] = mapped_column(String(1000))
    logo_path: Mapped[str | None] = mapped_column(String(500))
    logo_kind: Mapped[str] = mapped_column(String(16), default="country")
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(120))
    locale: Mapped[str | None] = mapped_column(String(8))
    theme: Mapped[str | None] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    profile: Mapped["UserProfile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class UserProfile(Base):
    __tablename__ = "user_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), unique=True)
    # Contact details live here ONLY and are never sent to the model.
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(60))
    address: Mapped[str | None] = mapped_column(String(500))
    date_of_birth: Mapped[str | None] = mapped_column(String(40))
    document_id: Mapped[str | None] = mapped_column(String(120))
    # Model-safe fields
    full_name: Mapped[str | None] = mapped_column(String(200))
    headline: Mapped[str | None] = mapped_column(String(300))
    summary: Mapped[str | None] = mapped_column(Text)
    experience: Mapped[list | None] = mapped_column(JSON, default=list)
    education: Mapped[list | None] = mapped_column(JSON, default=list)
    skills: Mapped[list | None] = mapped_column(JSON, default=list)
    languages: Mapped[list | None] = mapped_column(JSON, default=list)
    certifications: Mapped[list | None] = mapped_column(JSON, default=list)
    projects: Mapped[list | None] = mapped_column(JSON, default=list)
    nationality: Mapped[str | None] = mapped_column(String(120))
    current_location: Mapped[str | None] = mapped_column(String(200))
    target_countries: Mapped[list | None] = mapped_column(JSON, default=list)
    requires_sponsorship: Mapped[bool | None] = mapped_column(Boolean)
    preferred_language: Mapped[str | None] = mapped_column(String(8))
    ai_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="profile")


class SavedListing(Base):
    __tablename__ = "saved_listing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listing.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("user_id", "listing_id", name="uq_saved_user_listing"),)


class Document(Base):
    __tablename__ = "document"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(24), unique=True, index=True, default=new_public_id)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    listing_id: Mapped[int | None] = mapped_column(ForeignKey("listing.id", ondelete="SET NULL"), index=True)
    doc_type: Mapped[str] = mapped_column(String(16), index=True)  # cv/letter/motivation
    language: Mapped[str] = mapped_column(String(8), default="en")
    country_style: Mapped[str | None] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(400))
    content_json: Mapped[dict | None] = mapped_column(JSON)
    content_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ChatSession(Base):
    __tablename__ = "chat_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, default=new_public_id)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    visitor_token: Mapped[str | None] = mapped_column(String(64), index=True)
    locale: Mapped[str | None] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_session.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user/assistant/tool
    content: Mapped[str] = mapped_column(Text)
    tool_name: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LlmDailyUsage(Base):
    __tablename__ = "llm_daily_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[str] = mapped_column(String(10), index=True)  # Pacific date
    model_slot: Mapped[str] = mapped_column(String(16), index=True)  # fast/quality
    model_name: Mapped[str] = mapped_column(String(80))
    requests: Mapped[int] = mapped_column(Integer, default=0)
    background_requests: Mapped[int] = mapped_column(Integer, default=0)
    failures_429: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (UniqueConstraint("day", "model_slot", name="uq_usage_day_slot"),)


class LlmUserUsage(Base):
    __tablename__ = "llm_user_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[str] = mapped_column(String(10), index=True)
    identity: Mapped[str] = mapped_column(String(120), index=True)
    requests: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (UniqueConstraint("day", "identity", name="uq_usage_day_identity"),)


class TranslationCache(Base):
    __tablename__ = "translation_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listing.id", ondelete="CASCADE"), index=True)
    target_lang: Mapped[str] = mapped_column(String(8), index=True)
    text_html: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("listing_id", "target_lang", name="uq_translation_listing_lang"),)


class QueryTranslationCache(Base):
    __tablename__ = "query_translation_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    translated: Mapped[str] = mapped_column(String(400))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SourceRun(Base):
    __tablename__ = "source_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(60), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running")
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    accepted: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class ClickLog(Base):
    __tablename__ = "click_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listing.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    referrer: Mapped[str | None] = mapped_column(String(500))


class PushDevice(Base):
    """APNs device token for the iOS app.

    Tokens are only stored when the mobile API is enabled. The token is a
    per-install identifier, never a contact detail, and is deleted with the
    user's account.
    """

    __tablename__ = "push_device"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(400), unique=True, index=True)
    platform: Mapped[str] = mapped_column(String(16), default="ios")
    locale: Mapped[str | None] = mapped_column(String(8))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
