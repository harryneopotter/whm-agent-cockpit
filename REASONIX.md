# Cockpit — REASONIX.md

Auto-pinned session context.

## Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI (dashboard + API), APScheduler (collector scheduling)
- **Key deps**: httpx (WHM API + HTTP health), aiosqlite, pydantic-settings, tomli (policy engine)
- **Codex AI**: OpenAI API (GPT-4o) — Phase 6
- **Dashboard auth**: Tailscale (Tailscale-User-Name header)

## Layout

- `src/cockpit/` — application package
  - `collectors/` — polling agents (server health, services, HTTP health, WHM accounts, etc.)
  - `dashboard/` — FastAPI app for the human-facing operator UI
  - `api/` — `client_telemetry.py` (Phase 2.5 — client-safe read-only API)
  - `executor/` — action catalog + safe action runner
    - `handlers/` — deterministic script implementations (e.g. restart_exim)
  - `policy/` — `engine.py` reads TOML policy, gates auto-run decisions
  - `db/` — `migrate.py` — SQLite schema (15 migrations, WAL mode)
  - `config.py` — env-var config via pydantic-settings (COCKPIT_ prefix)
  - `whm_client.py` — WHM API v1 client (token auth)
- `config/` — example configs (`policy.example.toml`)
- `tests/` — pytest suite

## Commands

From `pyproject.toml` scripts:

| Command | Entry point |
|---------|-------------|
| `cockpit-collector` | `cockpit.collectors.runner:main` — run all collectors |
| `cockpit-dashboard` | `cockpit.dashboard.app:main` — operator UI on :8080 |
| `cockpit-executor` | `cockpit.executor.runner:main` — standalone executor |
| `cockpit-db-migrate` | `cockpit.db.migrate:main` — apply SQLite migrations |

Lint: `ruff check src/` — format: `ruff format src/` — test: `pytest`

## Conventions

- **Process separation** — three OS-level roles: collector (read-only), dashboard (reads DB, requests actions), executor (runs handlers). Codex review is separate.
- **Action catalog** — no generic actions (no RUN_COMMAND, EXEC_SHELL). Every action has an `action_id` + handler.
- **Policy engine** — 6-gate decision logic + circuit breaker (block_after_postcheck_failures). TOML config, version-controlled, not writable by automation.
- **Client-safe API** (Phase 2.5) — cache-first, returns stale immediately/queues refresh, never exposes operator data (LVE, Imunify, error logs, Codex recommendations).
- **Freshness** — every metric has `collected_at` + `ttl_seconds`. Online status = UNKNOWN after 5 min staleness.
- **Addendum applied** — `cockpit-final-prd-v2.md` has been updated with all 15 changes from `cockpit-prd-v2-required-changes-addendum.md`.

## Watch out for

- **Phase 2.5 client API must never be browser-callable** — server-side only via Next.js API routes/server components (addendum §3).
- **HTTP origin checks use `curl --resolve`**, not Host header over IP — avoids TLS SNI mismatch (addendum §5).
- **Whitelisted handlers only** — the executor runs Python callables in `handlers/`, never raw shell/scripts.
- **DB path** defaults to `/var/lib/cockpit/cockpit.db` — override via `COCKPIT_DB_PATH`.
- **Policy file missing = all auto-run blocked** — the engine falls back to safe defaults silently.
