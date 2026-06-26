# Cockpit

Internal WHM/cPanel hosting operations cockpit with supervised maintenance automation.

A production-safe system that monitors WHM/cPanel servers, shows clear operational status, supports safe manual actions, generates scheduled health reports, and allows an AI reviewer (Codex) to recommend only predefined deterministic actions through a strict action catalog.

## Stack

- **Python 3.11+** with **FastAPI** (dashboard + API)
- **httpx** — WHM API & HTTP health checks
- **APScheduler** — collector scheduling
- **SQLite** (WAL mode) — telemetry storage
- **pydantic-settings** — env-var config
- **Jinja2** — dashboard templates
- **OpenAI API** (GPT-4o) — Codex review (Phase 6)
- **Tailscale** — dashboard authentication
- **systemd** — process management

## Architecture

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

Everything runs on the **WHM server**. The only connection to the WHMCS server is the **Client Area Read-Only Telemetry API** — a server-side authenticated endpoint that the Next.js client area calls to display per-account stats to end users.

## Quick Start

```bash
# Clone the repo on the WHM server
git clone https://github.com/harryneopotter/whm-agent-cockpit.git /opt/cockpit
cd /opt/cockpit

# Run the interactive installer (as root)
bash deploy/install.sh
```

The installer will prompt for:
- **WHM API token** — generate one in WHM → API Tokens → Generate
- **Client API key** — shared secret for your Next.js server
- OpenAI API key (optional, for Phase 6 Codex review)
- Dashboard bind address/port

It creates:
- `cockpit` system user (no login, no home)
- `/etc/cockpit/cockpit.env` (chmod 600)
- `/etc/cockpit/policy.toml`
- `/var/lib/cockpit/cockpit.db`
- 3 systemd services (enabled and started)

## Services

| Service | Port | Purpose | Auth |
|---------|------|---------|------|
| `cockpit-dashboard` | 8080 | Operator UI | Tailscale |
| `cockpit-client-api` | 8081 | Client-safe telemetry API | Shared API key |
| `cockpit-collector` | — | Schedules all data collectors | None (local) |

Check logs: `journalctl -u cockpit-collector -f`

## Configuration

All config via environment variables with `COCKPIT_` prefix. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `COCKPIT_DB_PATH` | `/var/lib/cockpit/cockpit.db` | SQLite database path |
| `COCKPIT_WHM_HOST` | `localhost` | WHM server hostname |
| `COCKPIT_WHM_TOKEN` | — | WHM API token (required) |
| `COCKPIT_WHM_VERIFY_SSL` | `false` | Verify WHM SSL certificate |
| `COCKPIT_CLIENT_API_KEY` | — | Client area API key (required) |
| `COCKPIT_OPENAI_API_KEY` | — | OpenAI API key (Codex review, Phase 6) |
| `COCKPIT_TAILSCALE_AUTH_ENABLED` | `true` | Require Tailscale identity |
| `COCKPIT_POLICY_PATH` | `/etc/cockpit/policy.toml` | Policy file path |

## Dashboard Views

| Route | View |
|-------|------|
| `/` | Global dashboard — services, disk, memory, mail, backups, SSL, alerts |
| `/accounts` | Account list with live search |
| `/accounts/{user}` | Account detail — disk, bandwidth, health, SSL, suspension |
| `/mail` | Mail health — Exim/Dovecot, queue, frozen count |
| `/backups` | Backup health — JetBackup status, failed/missing |
| `/ssl` | SSL certificate expiry table |
| `/offenders` | Top LVE/CloudLinux resource users |
| `/audit` | Event log viewer |

## Client Telemetry API (Phase 2.5)

Used by the Next.js client area to display per-account stats. **Server-side only** — never exposed to the browser.

### Endpoints

```
GET  /api/v1/account/stats/{username}          # Single account
POST /api/v1/account/stats/batch               # Batch lookup
POST /api/v1/account/stats/{username}/refresh   # Request refresh
```

All endpoints require `X-API-Key` header with the shared secret.

### Response fields (client-safe)

- `request_id`, `server_id`, `username`
- `cached_at`, `collected_at`, `expires_at`, `freshness`
- `partial_data`, `warnings`
- `data`: disk_used_mb, disk_limit_mb, bandwidth_used_mb, bandwidth_limit_mb, email_count, db_count, subdomain_count, addon_domain_count, parked_domain_count, plan_name, account_status, online_status, ssl_valid, ssl_days_remaining

No operator data exposed (no LVE, Imunify, error logs, action history, Codex recommendations).

## Action Catalog

No generic actions. Every action has a registered `action_id`, handler, and policy:

| Action | Risk Tier | Target | Description |
|--------|-----------|--------|-------------|
| `RESTART_EXIM` | 1 (auto-fix) | service | Restart Exim mail |
| `RESTART_DOVECOT` | 1 (auto-fix) | service | Restart Dovecot |
| `RESTART_LITESPEED` | 1 (auto-fix) | service | Restart LiteSpeed (lsws) |
| `CHECK_SERVICE_STATUS` | 0 (read-only) | service | Check if a service is running |

## Policy Engine

TOML policy file at `/etc/cockpit/policy.toml`. Version-controlled, not writable by automation.

### Decision gates (auto mode)

1. Is the action **enabled** in policy?
2. Is `auto_run` true?
3. Have **consecutive detections** been met?
4. Has the **cooldown** passed?
5. Is the **rate limit** not exceeded?
6. Is the **circuit breaker** open? (fewer than `block_after_postcheck_failures` failures in 24h)

If any gate fails, the action is queued for operator approval.

### Fallback

If the policy file cannot be loaded, all auto-run defaults to `false`. Monitoring continues.

## Phases

| Phase | Status | What |
|-------|--------|------|
| 1: Collectors | ✅ Done | 10 collectors, SQLite storage, freshness tracking |
| 2: Dashboard | ✅ Done | 7 views, Tailscale auth, live DB queries |
| 2.5: Client API | ✅ Done | Cache-first, client-safe, joined tables, persistent refresh queue |
| 3: Action Catalog | ✅ Done | ActionDef + Executor + 4 registered actions |
| 4: Policy Engine | ✅ Done | TOML reader, 7-gate logic, circuit breaker |
| 5: Issue Lifecycle | ✅ Done | State machine, critical loop, 12h reports |
| 6: Codex Review | ✅ Done | OpenAI integration, structured reports |
| 7: Auto-Fix | ⏳ Post-MVP | Enable Tier 1 auto-fix with all safety gates |
| 8: Telegram | ⏳ Post-MVP | Signed action buttons, approval workflow |
| 9: Hardening | ⏳ Post-MVP | Emergency controls, self-monitoring, escalation rules |

## Development

```bash
# Install in dev mode
pip install -e .

# Run tests
pytest

# Lint
ruff check src/

# Format
ruff format src/

# Run collector (foreground)
cockpit-collector

# Run dashboard (foreground)
COCKPIT_DB_PATH=./dev.db COCKPIT_TAILSCALE_AUTH_ENABLED=false cockpit-dashboard

# Run client API (foreground)
COCKPIT_DB_PATH=./dev.db COCKPIT_CLIENT_API_KEY=dev-key cockpit-client-api

# Apply DB migrations
COCKPIT_DB_PATH=./dev.db cockpit-db-migrate
```

## Project Structure

```
src/cockpit/
├── api/              # Client Area Read-Only Telemetry API
├── collectors/       # Data polling agents (Phase 1)
├── dashboard/        # FastAPI dashboard + Jinja2 templates
├── db/               # SQLite schema migrations
├── executor/         # Action catalog + safe action runner
│   └── handlers/     # Deterministic action implementations
├── policy/           # TOML policy engine
├── config.py         # pydantic-settings config
├── codex.py          # Codex review pipeline (Phase 6)
├── issues.py         # Issue lifecycle state machine
├── reporting.py      # 12-hour report generator
└── whm_client.py     # WHM API v1 client
```

## Design Principles

- **AI can choose from buttons. Only the operator can create buttons.**
- No generic shell commands. Every action has a hardcoded handler.
- Policy engine is the single gatekeeper for automation.
- Every action, including rejections, is audited.
- Client-facing API is deliberately boring — no internal drama.
- Process separation: collector (read-only) ≠ executor (action runner) ≠ dashboard (UI).
