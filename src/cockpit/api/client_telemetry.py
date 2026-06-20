"""Client Area Read-Only Telemetry API (Phase 2.5 / MVP-B).

All endpoints return **client-safe schema only** — no operator data exposed.
Cache-first: returns stale/unknown immediately, queues background refresh.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

import sqlite3
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from cockpit.config import settings

logger = logging.getLogger(__name__)

# ── In-memory refresh queue ─────────────────────────────────────────────

_pending_refresh: set[str] = set()


async def _refresh_worker() -> None:
    """Background task: log pending refreshes every 30s for observability.

    In MVP, actual data refresh happens on the next collector cycle
    (every 3-10 min). This worker logs what's pending so operators
    can verify the queue is being consumed.
    """
    while True:
        await asyncio.sleep(30)
        if _pending_refresh:
            batch = list(_pending_refresh)
            logger.info("Refresh queue: %d pending accounts (%s)", len(batch), ", ".join(batch[:5]))
            _pending_refresh.clear()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if not settings.client_api_key:
        logger.error(
            "COCKPIT_CLIENT_API_KEY is not set — "
            "refusing to start. Set it in /etc/cockpit/cockpit.env"
        )
        raise RuntimeError("COCKPIT_CLIENT_API_KEY is required for production")
    logger.info("Client telemetry API starting")
    task = asyncio.create_task(_refresh_worker())
    yield
    task.cancel()
    logger.info("Client telemetry API stopped")


app = FastAPI(title="Cockpit Client Telemetry API", version="0.1.0", lifespan=lifespan)


# ── API key auth ────────────────────────────────────────────────────────


def _verify_key(x_api_key: str | None = Header(None, alias="X-API-Key")) -> None:
    """Refuse requests if API key is missing or wrong.

    Fail-closed: no key configured = refuse startup (see lifespan),
    so by the time a request arrives the key is guaranteed present.
    """
    if not x_api_key or x_api_key != settings.client_api_key:
        raise HTTPException(status_code=403, detail="invalid API key")


# ── DB helpers ──────────────────────────────────────────────────────────


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def _freshness_fields(
    collected_at: str | None, ttl_seconds: int
) -> tuple[str, str, str, str]:
    """Return (cached_at, collected_at, expires_at, freshness)."""
    now = datetime.now(timezone.utc)
    collected = (
        datetime.fromisoformat(collected_at)
        if collected_at else now
    )
    expires = collected + timedelta(seconds=ttl_seconds)
    age = (now - collected).total_seconds()
    freshness = "fresh" if age < ttl_seconds else "stale" if age < ttl_seconds * 2 else "unknown"
    return (
        now.isoformat(),
        collected.isoformat(),
        expires.isoformat(),
        freshness,
    )


# ── Response wrappers ───────────────────────────────────────────────────


def _account_response(username: str, row: sqlite3.Row | None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    cached_at = now.isoformat()

    if row is None:
        return {
            "request_id": str(uuid.uuid4()),
            "server_id": "",
            "username": username,
            "cached_at": cached_at,
            "collected_at": None,
            "expires_at": None,
            "freshness": "unknown",
            "partial_data": True,
            "warnings": ["no_data"],
            "data": None,
        }

    collected_at = row["collected_at"]
    ttl = row["ttl_seconds"]
    _, col_iso, expires_iso, freshness = _freshness_fields(collected_at, ttl)
    partial = False
    warnings: list[str] = []
    if freshness == "stale":
        warnings.append("data_stale")
        partial = True
    if freshness == "unknown":
        warnings.append("data_expired")
        partial = True

    # Client-safe fields only (addendum §2)
    data: dict[str, Any] = {
        "disk_used_mb": row["disk_used_mb"],
        "disk_limit_mb": row["disk_limit_mb"],
        "bandwidth_used_mb": row["bandwidth_used_mb"],
        "bandwidth_limit_mb": row["bandwidth_limit_mb"],
        "email_count": row["email_count"],
        "db_count": row["db_count"],
        "subdomain_count": row["subdomain_count"],
        "addon_domain_count": row["addon_domain_count"],
        "parked_domain_count": row["parked_domain_count"],
        "plan_name": row["plan_name"],
        "php_version": row["php_version"],
    }
    # Remove None values
    data = {k: v for k, v in data.items() if v is not None}

    return {
        "request_id": str(uuid.uuid4()),
        "server_id": "",
        "username": username,
        "cached_at": cached_at,
        "collected_at": col_iso,
        "expires_at": expires_iso,
        "freshness": freshness,
        "partial_data": partial,
        "warnings": warnings,
        "data": data,
    }


# ── Endpoints ───────────────────────────────────────────────────────────


@app.get("/api/v1/account/stats/{username}")
async def get_account_stats(
    username: str,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
):
    _verify_key(x_api_key)
    conn = _db()
    try:
        row = conn.execute(
            "SELECT * FROM account_stats WHERE username = ?", (username,)
        ).fetchone()
        return _account_response(username, row)
    finally:
        conn.close()


class BatchRequest(BaseModel):
    usernames: list[str]


@app.post("/api/v1/account/stats/batch")
async def batch_account_stats(
    body: BatchRequest,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
):
    _verify_key(x_api_key)
    conn = _db()
    try:
        results: dict[str, Any] = {}
        for username in body.usernames:
            row = conn.execute(
                "SELECT * FROM account_stats WHERE username = ?", (username,)
            ).fetchone()
            results[username] = _account_response(username, row)
            # Cache-first: if stale, queue background refresh (don't block response)
            if results[username]["freshness"] in ("stale", "unknown"):
                _pending_refresh.add(username)

        return {"results": results}
    finally:
        conn.close()


@app.post("/api/v1/account/stats/{username}/refresh")
async def refresh_account_stats(
    username: str,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
):
    _verify_key(x_api_key)
    # Enqueue refresh (actual refresh happens async in collector cycle)
    _pending_refresh.add(username)
    return {"status": "queued", "username": username}


def main() -> None:  # pragma: no cover
    uvicorn.run(
        "cockpit.api.client_telemetry:app",
        host=settings.client_api_host,
        port=settings.client_api_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
