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
- `config.py` — pydantic-settings, 18+ env vars with COCKPIT_ prefix
- `whm_client.py` — WHM API v1 client, token-only auth, `list_accounts()`
- `issues.py` — IssueManager with full state machine (10 states)
- `reporting.py` — ReportGenerator for Codex input reports
- `codex.py` — CodexReviewer, OpenAI API integration, structured JSON reports

#### Collectors (`src/cockpit/collectors/`)
- `base.py` — BaseCollector ABC with SQLite UPSERT, freshness tracking
- `server_health.py` — CPU/load/RAM/swap/disk/uptime from /proc
- `service_status.py` — systemctl checks (litespeed, exim, dovecot, mariadb, named)
- `whm_accounts.py` — WHM API listaccts, populates whm_accounts + suspension_status + account_stats
- `ssl_expiry.py` — Python ssl socket connect to :443 per domain (primary + addon/parked/sub via domain_mapping)
- `mail_queue.py` — exim -bpc, exim -bp, journalctl for errors
- `jetbackup.py` — JetBackup CLI checks (destination, last run, failed accounts, missing backups)
- `lve_stats.py` — lveinfo parser for resource offenders
- `http_health.py` — HTTP checks (HEAD→GET fallback) with concurrency, jitter, socket-based SSL cert extraction
- `critical_loop.py` — Immediate Critical Loop (5-min cycle, monitors / /home /var /tmp)
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
- `client_telemetry.py` — Cache-first, client-safe schema, joins account_stats + suspension + health + SSL

#### Executor (`src/cockpit/executor/`)
- `catalog.py` — ActionDef with related_issue_ids, post_check_service, mode=manual|auto
- `runner.py` — Executor with mode support, single-audit-entry, post-check with explicit service mapping
- `handlers/system.py` — restart_exim, restart_dovecot, restart_litespeed (lsws), check_service_status

#### Policy (`src/cockpit/policy/`)
- `engine.py` — TOML reader, mode=manual|auto, 7-gate logic (enabled→auto_run→detections→cooldown→rate_limit→circuit_breaker), safe fallback
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
- `tests/test_policy.py` — PolicyEngine tests with temp DB, cooldown enforcement

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

---

## Session 2: Review fixes (batch 1)

After first code review (`whmreview.md`):

### Issues fixed (6)
1. **Policy engine 3 TODO gates** → evaluate() queries issues table for consecutive detections, audit_log for cooldown + rate limits
2. **Executor missing post-check + audit** → Added `_post_check_service()`, `_audit_log()` writer, called after every execution
3. **COCKPI_DB_PATH typo** → Fixed → COCKPIT_DB_PATH
4. **Dead shutil loop** → Removed `for part in shutil.disk_usage("/"): pass`
5. **account_stats not populated** → WHMAccountsCollector now writes account_stats table
6. **Client API allowed unauthenticated** → Fail-closed: refuses startup if key unset; requests require valid key

### Corrected inaccuracies from first review
- HTTP concurrency, jitter, cache-first, client-safe schema were already implemented
- `cpanel.service` was never in the code

---

## Session 3: Review fixes (batch 2)

After second corrected review (`cockpitreview.md` → `cockpit-fixes.md`):

### Issues fixed (10)
1. **mode=manual vs mode=auto** → evaluate() takes mode param. Auto mode requires auto_run=true.
2. **Consecutive detection string guessing** → Uses related_issue_ids (explicit mapping) + optional issue_id param
3. **Cooldown timestamp naive vs aware** → Normalizes naive timestamps to UTC before subtraction
4. **Circuit breaker not enforced** → _check_circuit_breaker() counts action_failed events in 24h
5. **Rejected actions not audited** → Every return path in executor audits (_audit_log("action_rejected", ...))
6. **Post-check double-logged** → Single _audit_log() call at end, not inside post-check block
7. **LiteSpeed lsws vs litespeed** → post_check_service="lsws" field; post-check uses action field, not ID string
8. **Client API reads only account_stats** → _fetch_client_data() joins suspension_status + account_health + ssl_certs
9. **Fake refresh queue (in-memory, no work)** → Replaced with persistent refresh_requests SQLite table
10. **Origin check not implemented but claimed** → Removed origin_status from HTTP health output; docstring updated

### Additional fixes
- **WHM client**: Removed conflicting httpx.BasicAuth. Uses only Authorization: whm root:TOKEN. SSL verify configurable.
- **Audit log timestamps**: Executor writes explicit UTC ISO instead of SQLite naive datetime('now').

---

## Pending (Post-MVP)
- Phase 7: Tier 1 Auto-Fix enablement
- Phase 8: Telegram approval workflow (signed buttons, notifications)
- Phase 9: Hardening (self-monitoring, emergency controls, escalation rules)
- Telegram notification spec
- Complete escalation rule matrix
- `curl --resolve` origin-specific HTTP health checks
- Sudoers/helper design for deterministic action scripts (systemctl from unprivileged cockpit user)
