"""Background scheduler.

APScheduler runs the periodic ingestion and link-validation jobs in a worker
thread; each job drives its async implementation with ``asyncio.run`` so the
web event loop is never blocked. Starting twice (e.g. uvicorn --reload) is
harmless because the module keeps a single scheduler instance.
"""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _run(coro_factory) -> None:
    try:
        asyncio.run(coro_factory())
    except Exception:  # pragma: no cover - background failures must not kill the app
        log.exception("Scheduled job failed")


def _ingest_job() -> None:
    from app.ingest import run_ingestion

    result = asyncio.run(run_ingestion())
    log.info(
        "Ingestion finished: %s sources, %s fetched, %s accepted, %s errors",
        result.get("sources"),
        result.get("fetched"),
        result.get("accepted"),
        result.get("errors"),
    )


def _links_job() -> None:
    from app.links import check_overdue

    result = asyncio.run(check_overdue())
    log.info("Link check finished: %s", result)


def start_scheduler() -> BackgroundScheduler:
    """Create and start the singleton scheduler (idempotent)."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler

    scheduler = BackgroundScheduler(timezone="UTC", daemon=True)
    scheduler.add_job(
        _ingest_job,
        trigger=IntervalTrigger(minutes=max(5, settings.ingest_interval_minutes)),
        id="ingest",
        name="Fetch and store listings",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        _links_job,
        trigger=IntervalTrigger(hours=max(1, settings.link_check_interval_hours)),
        id="link-check",
        name="Revalidate apply links",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=900,
    )
    scheduler.start()
    _scheduler = scheduler
    log.info(
        "Scheduler started: ingestion every %s min, link checks every %s h",
        settings.ingest_interval_minutes,
        settings.link_check_interval_hours,
    )
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        finally:
            _scheduler = None
