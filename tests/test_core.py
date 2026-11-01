from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.i18n import is_rtl, load_catalog, western_digits
from app.models import Listing, VolunteerDetails
from app.search import SearchFilters, search_listings
from app.utils import sanitize_html
from app.visa.classifier import classify_job


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def add_listing(db, *, kind: str, title: str, fee: bool = False) -> Listing:
    row = Listing(
        listing_type=kind,
        title=title,
        company="Example Employer",
        source_name="test",
        is_active=True,
        visa_tier=2,
        visa_evidence="Visa sponsorship stated in the posting.",
        search_text=title.lower(),
    )
    db.add(row)
    db.flush()
    if kind == "volunteer":
        db.add(VolunteerDetails(listing_id=row.id, fee_required=fee, scam_flags=[]))
    return row


def test_jobs_and_volunteers_are_separate_and_fee_programmes_hidden(db_session):
    add_listing(db_session, kind="job", title="Sponsored nurse")
    add_listing(db_session, kind="volunteer", title="Volunteer nurse")
    add_listing(db_session, kind="volunteer", title="Fee volunteer", fee=True)
    db_session.commit()

    jobs, job_count = search_listings(db_session, SearchFilters(listing_type="job"))
    volunteers, volunteer_count = search_listings(
        db_session, SearchFilters(listing_type="volunteer")
    )

    assert job_count == 1
    assert [row.title for row in jobs] == ["Sponsored nurse"]
    assert volunteer_count == 1
    assert [row.title for row in volunteers] == ["Volunteer nurse"]


@pytest.mark.parametrize(
    "description",
    [
        "Visa sponsorship available. We are unable to sponsor candidates.",
        "Prise en charge du visa, mais pas de sponsoring.",
        "كفالة التأشيرة متاحة، لكن لا نوفر كفالة التأشيرة.",
    ],
)
def test_negative_sponsorship_language_overrides_positive(description):
    result = classify_job(
        title="Care worker",
        company="Example Employer",
        description=description,
        country_code="gb",
    )
    assert result.tier == 0
    assert result.negative


def test_explicit_sponsorship_phrase_is_tier_two():
    result = classify_job(
        title="Seasonal worker",
        company="Example Employer",
        description="Work visa provided for eligible seasonal workers.",
        country_code="gb",
    )
    assert result.tier == 2
    assert result.evidence


def test_sanitizer_accepts_provider_html_with_rel_attribute():
    cleaned = sanitize_html(
        '<p>Apply <a href="https://example.com/jobs" rel="nofollow">here</a>.</p>'
    )
    assert 'href="https://example.com/jobs"' in cleaned
    assert "noopener" in cleaned
    assert "<script" not in sanitize_html("<p>Ok</p><script>alert(1)</script>")


def test_official_register_match_is_country_scoped(monkeypatch):
    from app import visa
    from app.visa.registers import RegisterEntry

    class FakeRegisters:
        def match(self, company, country_code):
            if company == "Example Employer" and country_code == "gb":
                return RegisterEntry("Example Employer", "example employer", "gb", "worker", "UK register")
            return None

    monkeypatch.setattr(visa.classifier, "get_registers", lambda: FakeRegisters())
    arguments = {
        "title": "Care worker",
        "company": "Example Employer",
        "description": "",
        "source_flag": False,
    }
    assert classify_job(**arguments, country_code="gb").tier == 1
    assert classify_job(**arguments, country_code="us").tier == 0


def test_uk_register_refresh_uses_official_csv_and_normalizes_rows(monkeypatch, tmp_path):
    from app.visa import registers

    class FakeResponse:
        def __init__(self, *, text="", content=b""):
            self.text = text
            self.content = content

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, url):
            if url == registers.UK_REGISTER_PAGE:
                return FakeResponse(
                    text=(
                        '<a href="https://assets.publishing.service.gov.uk/latest.csv">'
                        "Register of Worker and Temporary Worker licensed sponsors</a>"
                    )
                )
            return FakeResponse(
                content=(
                    b"Organisation Name,Town/City,County,Type & Rating,Route\r\n"
                    b"Example Health Ltd,London,London,Worker (A rating),Skilled Worker\r\n"
                )
            )

    monkeypatch.setattr(registers, "REGISTER_DIR", tmp_path)
    monkeypatch.setattr(registers, "_store", registers.RegisterStore())
    monkeypatch.setattr(registers.httpx, "Client", FakeClient)

    result = registers.refresh_uk_register_if_stale()

    assert result == {"updated": True, "reason": "downloaded", "entries": 1}
    entry = registers.get_registers().match("Example Health Ltd", "gb")
    assert entry is not None
    assert entry.route == "Skilled Worker"
    assert entry.source == registers.UK_REGISTER_SOURCE


def test_catalogues_have_the_same_keys_and_arabic_is_rtl():
    catalogues = {lang: load_catalog(lang) for lang in ("en", "fr", "ar")}
    assert set(catalogues["en"]) == set(catalogues["fr"]) == set(catalogues["ar"])
    assert is_rtl("ar")
    assert not is_rtl("fr")
    assert western_digits("١٢٣") == "123"


def test_relative_time_accepts_iso_strings_from_api_cards():
    from app.i18n import translator_for

    for lang in ("en", "fr", "ar"):
        translator = translator_for(lang)
        assert translator.relative("2026-10-30T12:00:00+00:00")
        assert translator.relative("2026-10-30T12:00:00")  # naive SQLite value
        assert translator.relative("not-a-date") == ""


@pytest.mark.asyncio
async def test_quota_manager_enforces_rpm_with_local_database(monkeypatch):
    from app.llm import quota as quota_module

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(quota_module, "SessionLocal", factory)
    monkeypatch.setitem(quota_module.SLOTS, "fast", quota_module.SlotConfig(rpm=1, rpd=5))
    manager = quota_module.QuotaManager()

    await manager.acquire("fast", identity="test-visitor", model="test-model")
    with pytest.raises(quota_module.QuotaExceeded) as error:
        await manager.acquire("fast", identity="test-visitor", model="test-model", timeout=0)

    assert error.value.reason == "rpm"
    Base.metadata.drop_all(engine)
    engine.dispose()
