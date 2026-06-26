"""Client Area Read-Only Telemetry API (Phase 2.5 / MVP-B).

All endpoints return **client-safe schema only** — no operator data exposed.
Cache-first: returns stale/unknown immediately, writes refresh request to DB.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from cockpit.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if not settings.client_api_key:
        logger.error(
            "COCKPIT_CLIENT_API_KEY is not set — "
            "refusing to start. Set it in /etc/cockpit/cockpit.env"
        )
        raise RuntimeError("COCKPIT_CLIENT_API_KEY is required for production")
    logger.info("Client telemetry API starting")
    yield
    logger.info("Client telemetry API stopped")


app = FastAPI(title="Cockpit Client Telemetry API", version="0.1.0", lifespan=lifespan)


# ── API key auth ────────────────────────────────────────────────────────


def _verify_key(x_api_key: str | None = Header(None, alias="X-API-Key")) -> None:
    if not x_api_key or x_api_key != settings.client_api_key:
        raise HTTPException(status_code=403, detail="invalid API key")


# ── DB helpers ──────────────────────────────────────────────────────────


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def _freshness(collected_at: str | None, ttl_seconds: int) -> str:
    """Return 'fresh', 'stale', or 'unknown'."""
    if not collected_at:
        return "unknown"
    try:
        dt = datetime.fromisoformat(collected_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        if age < ttl_seconds:
            return "fresh"
        if age < ttl_seconds * 2:
            return "stale"
        return "unknown"
    except (ValueError, TypeError):
        return "unknown"


# ── Batch refresh table (persistent, not in-memory) ─────────────────────

_REFRESH_TABLE = """
CREATE TABLE IF NOT EXISTS refresh_requests (
    username TEXT PRIMARY KEY,
    requested_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0
)
"""


def _ensure_refresh_table() -> None:
    """Ensure the refresh_requests table exists."""
    conn = _db()
    try:
        conn.execute(_REFRESH_TABLE)
        conn.commit()
    finally:
        conn.close()


def _queue_refresh(username: str) -> None:
    """Write or update a refresh request to DB."""
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn = _db()
    try:
        conn.execute(
            "INSERT INTO refresh_requests (username, requested_at, attempts) "
            "VALUES (?, ?, 1) "
            "ON CONFLICT(username) DO UPDATE SET requested_at = ?, attempts = attempts + 1",
            (username, now, now),
        )
        conn.commit()
    finally:
        conn.close()


# ── Response builder with joined tables ─────────────────────────────────


def _fetch_client_data(username: str) -> dict[str, Any]:
    """Build a client-safe response by joining account_stats + suspension + health + SSL."""
    now = datetime.now(timezone.utc)
    cached_at = now.isoformat()
    conn = _db()
    try:
        # 1. Account stats
        stats = conn.execute(
            "SELECT * FROM account_stats WHERE username = ?", (username,)
        ).fetchone()

        if stats is None:
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

        collected = stats["collected_at"]
        ttl = stats["ttl_seconds"]
        freshness = _freshness(collected, ttl)
        expires = (
            datetime.fromisoformat(collected).replace(tzinfo=timezone.utc) + timedelta(seconds=ttl)
            if collected else now
        )
        partial = freshness in ("stale", "unknown")
        warnings: list[str] = []
        if freshness == "stale":
            warnings.append("data_stale")
        if freshness == "unknown":
            warnings.append("data_expired")

        # 2. Suspension status
        suspension = conn.execute(
            "SELECT * FROM suspension_status WHERE username = ?", (username,)
        ).fetchone()

        # 3. HTTP health
        health = conn.execute(
            "SELECT * FROM account_health WHERE username = ?", (username,)
        ).fetchone()

        # 4. SSL cert (latest for any domain matching this account)
        # First get the primary domain from stats
        account_domain = stats["primary_ip"]  # placeholder — actually get from whm_accounts
        ssl = None
        if account_domain:
            ssl = conn.execute(
                "SELECT * FROM ssl_certs WHERE domain = ? "
                "ORDER BY collected_at DESC LIMIT 1",
                (account_domain,),
            ).fetchone()

        # Client-safe data (addendum §2): no LVE, no Imunify, no error logs, no action history
        data: dict[str, Any] = {
            "disk_used_mb": stats["disk_used_mb"],
            "disk_limit_mb": stats["disk_limit_mb"],
            "bandwidth_used_mb": stats["bandwidth_used_mb"],
            "bandwidth_limit_mb": stats["bandwidth_limit_mb"],
            "email_count": stats["email_count"],
            "db_count": stats["db_count"],
            "subdomain_count": stats["subdomain_count"],
            "addon_domain_count": stats["addon_domain_count"],
            "parked_domain_count": stats["parked_domain_count"],
            "plan_name": stats["plan_name"],
            "account_status": "suspended" if (suspension and suspension["suspended"]) else "active",
            "account_status_checked_at": suspension["collected_at"] if suspension else None,
            "online_status": health["online_status"] if health else "UNKNOWN",
            "online_status_checked_at": health["collected_at"] if health else None,
            "online_response_time_ms": health["response_time_ms"] if health else None,
            "ssl_valid": ssl["days_remaining"] > 0 if ssl and ssl["days_remaining"] is not None else None,
            "ssl_days_remaining": ssl["days_remaining"] if ssl else None,
        }
        # Strip None values
        data = {k: v for k, v in data.items() if v is not None}

        return {
            "request_id": str(uuid.uuid4()),
            "server_id": "",
            "username": username,
            "cached_at": cached_at,
            "collected_at": collected,
            "expires_at": expires.isoformat(),
            "freshness": freshness,
            "partial_data": partial,
            "warnings": warnings,
            "data": data,
        }
    finally:
        conn.close()


# ── Endpoints ───────────────────────────────────────────────────────────


@app.get("/api/v1/account/stats/{username}")
async def get_account_stats(
    username: str,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
):
    _verify_key(x_api_key)
    result = _fetch_client_data(username)
    # Queue refresh if stale (single-account too)
    if result["freshness"] in ("stale", "unknown"):
        _queue_refresh(username)
    return result


class BatchRequest(BaseModel):
    usernames: list[str]


@app.post("/api/v1/account/stats/batch")
async def batch_account_stats(
    body: BatchRequest,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
):
    _verify_key(x_api_key)
    results: dict[str, Any] = {}
    for username in body.usernames:
        result = _fetch_client_data(username)
        results[username] = result
        if result["freshness"] in ("stale", "unknown"):
            _queue_refresh(username)
    return {"results": results}


@app.post("/api/v1/account/stats/{username}/refresh")
async def refresh_account_stats(
    username: str,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
):
    _verify_key(x_api_key)
    _queue_refresh(username)
    # Return the current cached state immediately (cache-first)
    result = _fetch_client_data(username)
    result["refresh_queued"] = True
    return result


def main() -> None:  # pragma: no cover
    _ensure_refresh_table()
    uvicorn.run(
        "cockpit.api.client_telemetry:app",
        host=settings.client_api_host,
        port=settings.client_api_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
