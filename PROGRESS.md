# Cockpit — Progress Log

## Session 1: Initial Build

### Documents consumed
- `cockpit-final-prd-v2.md` (1776 lines) — full PRD and implementation plan
- `cockpit-prd-v2-required-changes-addendum.md` (385 lines) — 15 required changes

### 13 architecture gaps identified
1. ❓ Tech stack → **Python / FastAPI** (user chose)
2. ❓ No database schema → **Built 15 SQLite migrations** (`src/cockpit/db/migrate.py`)
3. ❓ No internal API/communication spec → **Shared SQLite + process separation**
4. ❓ Codex integration undefined → **OpenAI API (GPT-4o)** (user chose)
5. ❓ No Telegram notification spec → **Deferred to Post-MVP Phase 8**
6. ❓ WHM API version + auth → **API 1 + token auth** (`src/cockpit/whm_client.py`)
7. ❓ Dashboard auth → **Tailscale** (user chose)
8. ❓ No testing strategy → **pytest + mock WHM responses** (`tests/`)
9. ❓ Action handler format → **Python callables in `handlers/`**
10. ❓ Retention policy → **14-day default, env-configured**
11. ❓ Phase 2.5 dependency map → **Uses Phase 1 collectors only; parallel-safe**
12. ❓ Escalation rules → **Examples documented, full spec deferred**
13. ❓ Collector scheduling framework → **APScheduler in asyncio event loop**

### PRD amendments applied (all 15 from addendum)
1. Phase 2.5 renamed → "Client Area Read-Only Telemetry API"
2. Client-safe vs Operator schemas added
3. Client API security strengthened (server-side only, key rotation, rate limits)
4. Cache-first approach (return stale, queue refresh)
5. SNI-safe HTTPS origin checks (`curl --resolve`)
6. HTTP status classification expanded (UP, REACHABLE_PROTECTED, REACHABLE_NOT_FOUND, DEGRADED, DOWN, SSL_ERROR, UNKNOWN)
7. HTTP collector guardrails (concurrency, jitter, retry, timeout, UA)
8. Suspension status via `listaccts` (not per-account)
9. Policy circuit breaker fields (`block_after_postcheck_failures`, `require_manual_ack_after_failure`)
10. Mandatory `notify_after = true` for all auto-run
11. Client API response discipline (`request_id`, `expires_at`, `partial_data`, `warnings`)
12. Future AI client context endpoint documented
13. Hybrid deployment = recommended MVP topology
14. Phase boundaries clarified (MVP-A: Phases 1-6, MVP-B: Phase 2.5)
15. Final rule: "Client API must be boring"

### Files created

#### Project root
- `pyproject.toml` — Python 3.11+, FastAPI, APScheduler, httpx, ruff, pytest
- `.gitignore`
- `REASONIX.md` — auto-pinned session context
- `PROGRESS.md` — this file

#### Core package (`src/cockpit/`)
- `__init__.py`
- `config.py` — pydantic-settings, 18 env vars with COCKPIT_ prefix
- `whm_client.py` — WHM API v1 client, token auth, `list_accounts()`
- `issues.py` — IssueManager with full state machine (10 states)
- `reporting.py` — ReportGenerator for Codex input reports
- `codex.py` — CodexReviewer, OpenAI API integration, structured JSON reports

#### Collectors (`src/cockpit/collectors/`)
- `base.py` — BaseCollector ABC with SQLite UPSERT, freshness tracking
- `server_health.py` — CPU/load/RAM/swap/disk/uptime from /proc
- `service_status.py` — systemctl checks (litespeed, exim, dovecot, mariadb, named)
- `whm_accounts.py` — WHM API listaccts, populates whm_accounts + suspension_status
- `ssl_expiry.py` — Python ssl socket connect to :443 per domain
- `mail_queue.py` — exim -bpc, exim -bp, journalctl for errors
- `jetbackup.py` — JetBackup CLI checks (destination, last run)
- `lve_stats.py` — lveinfo parser for resource offenders
- `http_health.py` — SNI-safe HTTP checks with concurrency, jitter, rich classification
- `critical_loop.py` — Immediate Critical Loop (5-min cycle)
- `runner.py` — APScheduler runner with migration auto-run at startup

#### Dashboard (`src/cockpit/dashboard/`)
- `app.py` — FastAPI, Tailscale auth middleware, 8 routes with live DB queries
- `templates/base.html` — Dark theme, responsive sidebar nav
- `templates/dashboard.html` — Global dashboard (services, disk, memory, mail, backups, SSL, alerts)
- `templates/accounts.html` — Account list with live JS search
- `templates/account_detail.html` — Per-account view (disk, bandwidth, health, SSL, suspension)
- `templates/mail.html` — Exim/Dovecot status + queue metrics
- `templates/backups.html` — JetBackup status + failed/missing accounts
- `templates/ssl.html` — SSL expiry table with colour-coded badges
- `templates/offenders.html` — LVE resource fault table
- `templates/audit.html` — Audit log event viewer

#### Client Telemetry API (`src/cockpit/api/`)
- `client_telemetry.py` — Cache-first, client-safe schema, request_id/freshness/partial_data

#### Executor (`src/cockpit/executor/`)
- `catalog.py` — ActionDef dataclass, in-memory registry, validation
- `runner.py` — Executor with 5-gate flow (validate → policy → dry-run → execute → log)
- `handlers/system.py` — restart_exim, restart_dovecot, restart_litespeed, check_service_status

#### Policy (`src/cockpit/policy/`)
- `engine.py` — TOML reader, 6-gate decision logic, circuit breaker, safe fallback
- `config/policy.example.toml` — Example policy with all fields

#### Database
- `src/cockpit/db/migrate.py` — 15 migrations covering all 17 tables

#### Deploy
- `deploy/install.sh` — Interactive installer (prompts for WHM token, client key, etc.)
- `deploy/.env.example` — Documented env var reference
- `deploy/cockpit-collector.service` — systemd unit (restart: always, NoNewPrivileges, 256M)
- `deploy/cockpit-dashboard.service` — systemd unit (512M)
- `deploy/cockpit-client-api.service` — systemd unit (256M)

#### Tests
- `tests/test_whm_client.py` — WHMAccount creation, _int_or_none
- `tests/test_policy.py` — PolicyEngine loading, auto-run, disabled action handling

### Deployment topology
```
WHM SERVER (production)              WHMCS SERVER
┌─────────────────────────────┐     ┌──────────────────┐
│ cockpit-collector           │     │ Next.js Client   │
│ cockpit-dashboard (:8080)   │     │ Area             │
│ cockpit-executor            │     │                  │
│ policy engine               │     │ (server-side)    │
│ Codex review (OpenAI)       │     │       │          │
│ Cockpit DB (SQLite)         │     │       │ API key  │
│ client-telemetry API (:8081)│────>│       ▼          │
└─────────────────────────────┘     └──────────────────┘
```

### Pending (Post-MVP)
- Phase 7: Tier 1 Auto-Fix enablement
- Phase 8: Telegram approval workflow (signed buttons, notifications)
- Phase 9: Hardening (self-monitoring, emergency controls, escalation rules)
- Telegram notification spec
- Complete escalation rule matrix
