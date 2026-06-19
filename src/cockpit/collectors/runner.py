"""Collector runner — schedules and runs all collectors."""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from cockpit.collectors.server_health import ServerHealthCollector
from cockpit.collectors.service_status import ServiceStatusCollector
from cockpit.collectors.critical_loop import CriticalLoopCollector
from cockpit.collectors.http_health import HTTPHealthCollector
from cockpit.collectors.whm_accounts import WHMAccountsCollector
from cockpit.collectors.ssl_expiry import SSLExpiryCollector
from cockpit.collectors.mail_queue import MailQueueCollector
from cockpit.collectors.jetbackup import JetBackupCollector
from cockpit.collectors.lve_stats import LVEStatsCollector
from cockpit.config import settings
from cockpit.db.migrate import main as migrate_db

logger = logging.getLogger(__name__)


async def main() -> None:  # pragma: no cover
    """Entry point: run all collectors on their schedules."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Run migrations at startup
    try:
        migrate_db()
        logger.info("Database schema up to date")
    except Exception as exc:
        logger.error("Migration failed: %s — continuing anyway", exc)

    scheduler = AsyncIOScheduler()

    # ── Phase 1: Core OS collectors ──────────────────────────────────
    scheduler.add_job(
        ServerHealthCollector().run, "interval",
        seconds=60, id="server_health", max_instances=1,
    )
    scheduler.add_job(
        ServiceStatusCollector().run, "interval",
        seconds=120, id="service_status", max_instances=1,
    )

    # ── Phase 1: WHM API collectors ──────────────────────────────────
    scheduler.add_job(
        WHMAccountsCollector().run, "interval",
        seconds=600, id="whm_accounts", max_instances=1,
    )
    scheduler.add_job(
        MailQueueCollector().run, "interval",
        seconds=120, id="mail_queue", max_instances=1,
    )
    scheduler.add_job(
        SSLExpiryCollector().run, "interval",
        seconds=3600, id="ssl_expiry", max_instances=1,
    )
    scheduler.add_job(
        JetBackupCollector().run, "interval",
        seconds=600, id="jetbackup", max_instances=1,
    )
    scheduler.add_job(
        LVEStatsCollector().run, "interval",
        seconds=300, id="lve_stats", max_instances=1,
    )

    # ── Phase 5: Critical monitoring loop ────────────────────────────
    scheduler.add_job(
        CriticalLoopCollector().run, "interval",
        seconds=settings.collector_interval_critical_loop,
        id="critical_loop", max_instances=1,
    )

    # ── Phase 2.5: HTTP health checks ────────────────────────────────
    scheduler.add_job(
        HTTPHealthCollector().run, "interval",
        seconds=settings.collector_interval_http_health,
        id="http_health", max_instances=1,
    )

    scheduler.start()
    logger.info("Collector runner started with %d jobs", len(scheduler.get_jobs()))
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
