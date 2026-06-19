"""Cockpit Dashboard — FastAPI app with Tailscale auth and Jinja2 templates."""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from cockpit.config import settings

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

WHM_HOST = settings.whm_host


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


# ── Tailscale auth middleware ───────────────────────────────────────────

TAILSCALE_HEADER = "Tailscale-User-Name"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Cockpit dashboard starting (Tailscale auth=%s)", settings.tailscale_auth_enabled)
    yield


app = FastAPI(title="Cockpit Dashboard", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def tailscale_auth(request: Request, call_next):
    if settings.tailscale_auth_enabled:
        user = request.headers.get(TAILSCALE_HEADER)
        if not user:
            return JSONResponse(status_code=401, content={"detail": "Tailscale authentication required"})
    return await call_next(request)


# ── Helpers ─────────────────────────────────────────────────────────────


def _freshness_status(collected_at: str | None, ttl: int | None) -> str:
    if not collected_at or not ttl:
        return "unknown"
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(collected_at)
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        return "fresh" if age < ttl else "stale" if age < ttl * 2 else "unknown"
    except Exception:
        return "unknown"


# ── Routes ──────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def global_dashboard(request: Request):
    conn = _db()
    try:
        # Server health
        row = conn.execute("SELECT * FROM server_health ORDER BY collected_at DESC LIMIT 1").fetchone()
        server = dict(row) if row else {}

        # Services
        svc_rows = conn.execute(
            "SELECT DISTINCT service_name, status FROM service_status "
            "WHERE collected_at = (SELECT MAX(collected_at) FROM service_status)"
        ).fetchall()
        services = [{"name": r["service_name"], "status": r["status"]} for r in svc_rows]

        # Disk
        disk_row = conn.execute(
            "SELECT * FROM disk_health WHERE mount_point = '/' ORDER BY collected_at DESC LIMIT 1"
        ).fetchone()
        disk = dict(disk_row) if disk_row else {}

        # Mail
        mail_row = conn.execute("SELECT * FROM mail_queue ORDER BY collected_at DESC LIMIT 1").fetchone()
        mail = dict(mail_row) if mail_row else {}

        # Backups
        bk_row = conn.execute("SELECT * FROM jetbackup_status ORDER BY collected_at DESC LIMIT 1").fetchone()
        backups = dict(bk_row) if bk_row else {}
        if backups.get("failed_accounts"):
            try:
                backups["failed_accounts"] = json.loads(backups["failed_accounts"])
            except (json.JSONDecodeError, TypeError):
                backups["failed_accounts"] = []
        if backups.get("accounts_missing_recent_backup"):
            try:
                backups["accounts_missing_recent_backup"] = json.loads(backups["accounts_missing_recent_backup"])
            except (json.JSONDecodeError, TypeError):
                backups["accounts_missing_recent_backup"] = []

        # SSL
        ssl_rows = conn.execute(
            "SELECT domain, days_remaining FROM ssl_certs "
            "WHERE days_remaining IS NOT NULL AND days_remaining <= 14 "
            "AND collected_at = (SELECT MAX(collected_at) FROM ssl_certs)"
        ).fetchall()
        ssl = {"expiring_within_14_days": [{"domain": r["domain"], "days_remaining": r["days_remaining"]} for r in ssl_rows]}

        # Active alerts
        alert_rows = conn.execute(
            "SELECT issue_id, severity, state, detected_at, consecutive_detections, description "
            "FROM issues WHERE state NOT IN ('RESOLVED', 'SUPPRESSED') "
            "ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, detected_at DESC"
        ).fetchall()
        alerts = [dict(r) for r in alert_rows]

        return templates.TemplateResponse("dashboard.html", {
            "request": request, "active": "dashboard",
            "server": server, "services": services, "disk": disk,
            "mail": mail, "backups": backups, "ssl": ssl, "alerts": alerts,
        })
    finally:
        conn.close()


@app.get("/accounts", response_class=HTMLResponse)
async def account_list(request: Request):
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT username, domain, plan_name, disk_used_mb, disk_limit_mb, "
            "suspended, php_version FROM whm_accounts ORDER BY username"
        ).fetchall()
        accounts = [dict(r) for r in rows]
        return templates.TemplateResponse("accounts.html", {
            "request": request, "active": "accounts", "accounts": accounts,
        })
    finally:
        conn.close()


@app.get("/accounts/{username}", response_class=HTMLResponse)
async def account_detail(request: Request, username: str):
    conn = _db()
    try:
        row = conn.execute(
            "SELECT * FROM whm_accounts WHERE username = ?", (username,)
        ).fetchone()
        if not row:
            return HTMLResponse("Account not found", status_code=404)
        acct = dict(row)

        disk_percent = round(acct["disk_used_mb"] / acct["disk_limit_mb"] * 100, 1) if acct.get("disk_limit_mb") and acct["disk_limit_mb"] > 0 else None
        bw_percent = round(acct["bandwidth_used_mb"] / acct["bandwidth_limit_mb"] * 100, 1) if acct.get("bandwidth_limit_mb") and acct["bandwidth_limit_mb"] > 0 else None

        health_row = conn.execute(
            "SELECT * FROM account_health WHERE username = ?", (username,)
        ).fetchone()
        health = dict(health_row) if health_row else None
        if health and health.get("collected_at"):
            health["freshness"] = _freshness_status(health["collected_at"], health.get("ttl_seconds"))

        suspension = conn.execute(
            "SELECT * FROM suspension_status WHERE username = ?", (username,)
        ).fetchone()
        suspension = dict(suspension) if suspension else None

        return templates.TemplateResponse("account_detail.html", {
            "request": request, "active": "accounts",
            "acct": acct, "disk_percent": disk_percent, "bw_percent": bw_percent,
            "health": health, "suspension": suspension, "whm_host": WHM_HOST,
        })
    finally:
        conn.close()


@app.get("/mail", response_class=HTMLResponse)
async def mail_health(request: Request):
    conn = _db()
    try:
        mail_row = conn.execute("SELECT * FROM mail_queue ORDER BY collected_at DESC LIMIT 1").fetchone()
        mail = dict(mail_row) if mail_row else {}

        svc_rows = conn.execute(
            "SELECT service_name, status FROM service_status "
            "WHERE service_name IN ('exim', 'dovecot') "
            "AND collected_at = (SELECT MAX(collected_at) FROM service_status)"
        ).fetchall()
        services = {r["service_name"]: r["status"] for r in svc_rows}

        return templates.TemplateResponse("mail.html", {
            "request": request, "active": "mail",
            "mail": mail, "services": services, "whm_host": WHM_HOST,
        })
    finally:
        conn.close()


@app.get("/backups", response_class=HTMLResponse)
async def backup_health(request: Request):
    conn = _db()
    try:
        row = conn.execute("SELECT * FROM jetbackup_status ORDER BY collected_at DESC LIMIT 1").fetchone()
        backups = dict(row) if row else {}
        for field in ("failed_accounts", "accounts_missing_recent_backup"):
            if backups.get(field):
                try:
                    backups[field] = json.loads(backups[field])
                except (json.JSONDecodeError, TypeError):
                    backups[field] = []
        return templates.TemplateResponse("backups.html", {
            "request": request, "active": "backups",
            "backups": backups, "whm_host": WHM_HOST,
        })
    finally:
        conn.close()


@app.get("/ssl", response_class=HTMLResponse)
async def ssl_status(request: Request):
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT domain, days_remaining, issuer FROM ssl_certs "
            "WHERE collected_at = (SELECT MAX(collected_at) FROM ssl_certs) "
            "ORDER BY days_remaining ASC NULLS LAST"
        ).fetchall()
        certs = [dict(r) for r in rows]
        return templates.TemplateResponse("ssl.html", {
            "request": request, "active": "ssl", "certs": certs,
        })
    finally:
        conn.close()


@app.get("/offenders", response_class=HTMLResponse)
async def resource_offenders(request: Request):
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT * FROM lve_stats ORDER BY cpu_faults DESC NULLS LAST LIMIT 50"
        ).fetchall()
        lve = [dict(r) for r in rows]
        return templates.TemplateResponse("offenders.html", {
            "request": request, "active": "offenders", "lve": lve,
        })
    finally:
        conn.close()


@app.get("/audit", response_class=HTMLResponse)
async def audit_log(request: Request):
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 200"
        ).fetchall()
        entries = [dict(r) for r in rows]
        return templates.TemplateResponse("audit.html", {
            "request": request, "active": "audit", "entries": entries,
        })
    finally:
        conn.close()


def main() -> None:  # pragma: no cover
    uvicorn.run(
        "cockpit.dashboard.app:app",
        host=settings.dashboard_host,
        port=settings.dashboard_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
