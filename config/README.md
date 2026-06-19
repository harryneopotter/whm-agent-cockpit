# Cockpit Configuration

## Policy

- `policy.example.toml` — example policy config. Copy to `/etc/cockpit/policy.toml`.

## Environment variables

All config is via env vars prefixed with `COCKPIT_`. See `src/cockpit/config.py` for the full list.

Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `COCKPIT_DB_PATH` | `/var/lib/cockpit/cockpit.db` | SQLite database path |
| `COCKPIT_WHM_HOST` | `localhost` | WHM server hostname |
| `COCKPIT_WHM_TOKEN` | — | WHM API token |
| `COCKPIT_CLIENT_API_KEY` | — | Client area API key (Phase 2.5) |
| `COCKPIT_OPENAI_API_KEY` | — | OpenAI API key (Codex review, Phase 6) |
| `COCKPIT_TAILSCALE_AUTH_ENABLED` | `true` | Require Tailscale identity for dashboard |
