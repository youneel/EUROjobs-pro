"""Central LLM quota manager shared by every web worker and background job.

- Async token bucket for requests-per-minute.
- Persisted daily counters with a Pacific-midnight reset.
- Per-user/per-IP daily budget.
- Background tasks may only use LLM_BACKGROUND_SHARE of each model's daily quota.
- On daily exhaustion the slot is marked exhausted; callers fall back once to
  the other model, then degrade gracefully (no retry loops).
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import LlmDailyUsage, LlmUserUsage
from app.security import pacific_reset_utc, utc_today_pacific


class QuotaExceeded(RuntimeError):
    def __init__(self, reason: str, reset_at: datetime | None = None, slot: str = "fast"):
        super().__init__(reason)
        self.reason = reason  # rpm | daily | user | background | disabled
        self.reset_at = reset_at or pacific_reset_utc()
        self.slot = slot


@dataclass
class SlotConfig:
    rpm: int
    rpd: int


SLOTS = {
    "fast": SlotConfig(settings.llm_rpm_fast, settings.llm_rpd_fast),
    "quality": SlotConfig(settings.llm_rpm_quality, settings.llm_rpd_quality),
}


class QuotaManager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._minute: dict[str, list[float]] = {"fast": [], "quality": []}
        self._exhausted: dict[str, str] = {}  # slot -> day

    # -- persistence helpers ------------------------------------------------
    @staticmethod
    def _usage_row(db: Session, day: str, slot: str, model: str) -> LlmDailyUsage:
        row = db.scalar(
            select(LlmDailyUsage).where(LlmDailyUsage.day == day, LlmDailyUsage.model_slot == slot)
        )
        if row is None:
            row = LlmDailyUsage(day=day, model_slot=slot, model_name=model, requests=0)
            db.add(row)
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                row = db.scalar(
                    select(LlmDailyUsage).where(
                        LlmDailyUsage.day == day, LlmDailyUsage.model_slot == slot
                    )
                )
        return row

    def _reset_minute_window(self, slot: str, now: float) -> None:
        bucket = [stamp for stamp in self._minute[slot] if now - stamp < 60.0]
        self._minute[slot] = bucket

    # -- public API ---------------------------------------------------------
    async def acquire(
        self,
        slot: str,
        *,
        identity: str | None = None,
        background: bool = False,
        timeout: float = 12.0,
        model: str = "",
    ) -> None:
        """Reserve one request. Waits briefly for RPM; raises QuotaExceeded."""
        if slot not in SLOTS:
            raise ValueError(f"unknown slot {slot}")
        config = SLOTS[slot]
        if config.rpd <= 0 or config.rpm <= 0:
            raise QuotaExceeded("disabled", slot=slot)
        deadline = time.monotonic() + max(0.0, timeout)
        day = utc_today_pacific()

        while True:
            async with self._lock:
                if self._exhausted.get(slot) == day:
                    raise QuotaExceeded("daily", slot=slot)
                now = time.monotonic()
                self._reset_minute_window(slot, now)
                if len(self._minute[slot]) >= config.rpm:
                    wait = 60.0 - (now - self._minute[slot][0]) + 0.05
                    if time.monotonic() + wait > deadline:
                        raise QuotaExceeded("rpm", slot=slot)
                    await asyncio.sleep(min(wait, 1.0) + random.uniform(0, 0.15))
                    continue

                # Persist daily and per-user counters atomically enough for a
                # single-process deployment. PostgreSQL serialises with the
                # unique constraints; SQLite serialises writers.
                db = SessionLocal()
                try:
                    row = self._usage_row(db, day, slot, model)
                    if row.requests >= config.rpd:
                        self._exhausted[slot] = day
                        db.commit()
                        raise QuotaExceeded("daily", slot=slot)
                    if background:
                        cap = int(config.rpd * max(0.0, min(1.0, settings.llm_background_share)))
                        if row.background_requests >= cap:
                            db.commit()
                            raise QuotaExceeded("background", slot=slot)
                    if identity and not background:
                        limit = settings.llm_user_daily_limit
                        user_row = db.scalar(
                            select(LlmUserUsage).where(
                                LlmUserUsage.day == day, LlmUserUsage.identity == identity
                            )
                        )
                        if user_row is None:
                            user_row = LlmUserUsage(day=day, identity=identity, requests=0)
                            db.add(user_row)
                            db.flush()
                        if limit > 0 and user_row.requests >= limit:
                            db.commit()
                            raise QuotaExceeded("user", slot=slot)
                        user_row.requests += 1
                    row.requests += 1
                    if background:
                        row.background_requests += 1
                    db.commit()
                except QuotaExceeded:
                    raise
                except Exception:
                    db.rollback()
                    raise QuotaExceeded("daily", slot=slot)
                finally:
                    db.close()

                self._minute[slot].append(now)
                return

    def record_429(self, slot: str, daily: bool = False) -> None:
        day = utc_today_pacific()
        if daily:
            self._exhausted[slot] = day
        db = SessionLocal()
        try:
            row = self._usage_row(db, day, slot, "")
            row.failures_429 += 1
            count = row.failures_429
            db.commit()
            # Repeated 429s inside one minute strongly suggest the daily limit.
            if count >= 5:
                self._exhausted[slot] = day
        finally:
            db.close()

    def record_tokens(self, slot: str, input_tokens: int = 0, output_tokens: int = 0, model: str = "") -> None:
        day = utc_today_pacific()
        db = SessionLocal()
        try:
            row = self._usage_row(db, day, slot, model)
            row.input_tokens += max(0, int(input_tokens or 0))
            row.output_tokens += max(0, int(output_tokens or 0))
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def status(self, slot: str) -> dict:
        day = utc_today_pacific()
        config = SLOTS.get(slot, SlotConfig(0, 0))
        db = SessionLocal()
        try:
            row = db.scalar(
                select(LlmDailyUsage).where(LlmDailyUsage.day == day, LlmDailyUsage.model_slot == slot)
            )
            used = row.requests if row else 0
            background_used = row.background_requests if row else 0
            failures = row.failures_429 if row else 0
        finally:
            db.close()
        return {
            "slot": slot,
            "limit": config.rpd,
            "used": used,
            "remaining": max(0, config.rpd - used),
            "background_used": background_used,
            "background_cap": int(config.rpd * settings.llm_background_share),
            "failures_429": failures,
            "exhausted": self._exhausted.get(slot) == day,
            "resets_at": pacific_reset_utc(),
        }

    def user_remaining(self, identity: str | None) -> int:
        if not identity:
            return settings.llm_user_daily_limit
        day = utc_today_pacific()
        db = SessionLocal()
        try:
            row = db.scalar(
                select(LlmUserUsage).where(
                    LlmUserUsage.day == day, LlmUserUsage.identity == identity
                )
            )
            used = row.requests if row else 0
        finally:
            db.close()
        return max(0, settings.llm_user_daily_limit - used)

    def any_available(self) -> bool:
        return any(self.status(slot)["remaining"] > 0 for slot in SLOTS)


quota = QuotaManager()


def reset_daily_cache() -> None:
    """Used by tests or an admin action after a Pacific-midnight rollover."""
    quota._exhausted.clear()
    quota._minute = {"fast": [], "quality": []}


def seconds_until_reset() -> int:
    return max(0, int((pacific_reset_utc() - datetime.now(pacific_reset_utc().tzinfo)).total_seconds()))
