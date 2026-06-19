# Cockpit PRD v2 — Required Changes Addendum

Use this addendum to update `cockpit-final-prd-v2.md` before implementation.

## 1. Reframe Phase 2.5

Rename:

> Phase 2.5: Client Area Stats API

to:

> Phase 2.5: Client Area Read-Only Telemetry API

Reason:

This API is not random scope creep. It powers the custom BluePandaHosting AI-assisted WHMCS/Next.js client area.

It must be treated as a **client-safe read-only projection** of Cockpit telemetry, not as part of the internal operator dashboard.

Architecture:

```text
Cockpit Internal Ops
  - full telemetry
  - operator dashboard
  - safe actions
  - Codex review
  - reports
  - alerts
  - audit logs

Client Area Read-Only Telemetry API
  - client-safe stats only
  - account status
  - basic health
  - freshness indicators
  - no actions
  - no internal details
```

## 2. Add Client-Safe vs Operator Schemas

Add a hard separation between internal/operator data and client-facing data.

### Operator Account Schema

Used only inside Cockpit dashboard.

May include:

- full account telemetry
- LVE/resource faults
- server mapping
- resource offender data
- backup warning details
- error log hints
- Imunify details
- WHM/cPanel/JetBackup links
- action buttons
- Codex recommendations
- audit/action history

### Client-Safe Account Schema

Used only by the BluePandaHosting client area.

Allowed fields:

- cPanel username
- primary domain
- plan name
- account status: active/suspended/unknown
- disk used/limit/percent
- bandwidth used/limit/percent
- email/database/subdomain/addon-domain counts
- website status: UP/DEGRADED/DOWN/UNKNOWN
- SSL status: valid/expiring/expired/error/unknown
- SSL days remaining
- last updated / freshness
- simple client-safe warning labels

Do not expose client-side:

- server IP unless explicitly needed
- internal hostname
- other accounts on server
- Exim queue details
- LVE abuse labels
- resource offender rankings
- raw error logs
- Imunify raw findings
- backup destination details
- JetBackup internals
- action history
- Codex recommendations
- policy decisions
- audit logs

Client-facing wording must be support-safe.

Example:

Use:

> Your site may need optimization.

Do not use:

> Your account is causing IO faults.

## 3. Strengthen Client Area API Security

Current shared API key approach is acceptable only with additional guardrails.

Add these requirements:

- Cockpit Client Area API must never be callable from the browser.
- Next.js must call Cockpit server-side only, via API routes or server components.
- The shared API key must be read-only and scoped only to client-safe telemetry endpoints.
- The action/executor API must use separate credentials and must never share this key.
- Restrict access by private network, Tailscale, Cloudflare Access, or source IP allowlist wherever possible.
- Add API key rotation support.
- Add per-endpoint rate limits.
- Log every request.
- Never accept usernames directly from browser/user input.
- Usernames must come from WHMCS `GetClientsProducts` for the authenticated client.
- If exposed outside a private network, add HMAC signing with timestamp/nonce to prevent replay.

## 4. Make Client API Cache-First

Do not hammer WHM/cPanel synchronously during client area requests.

Replace:

> Cache misses must be fetched in parallel.

with:

> Client-area telemetry API should primarily read cached Cockpit data. Cache misses or stale records should enqueue a refresh job and return stale/unknown data immediately.

Recommended behavior:

```text
Client area requests account stats
↓
Cockpit returns cached data immediately
↓
If data is stale/missing, Cockpit queues refresh
↓
Next.js revalidates shortly after
```

Manual refresh endpoint may request a refresh, but should still rate-limit and avoid blocking on expensive WHM/API/HTTP checks unless explicitly configured.

## 5. Fix HTTPS Origin Health Check

For origin checks against a server IP, do not use:

```text
GET https://{server_ip}/ with Host: {primary_domain}
```

This can fail due to TLS SNI mismatch.

Use SNI-safe resolution instead:

```bash
curl --resolve example.com:443:SERVER_IP https://example.com/
```

This preserves:

- hostname
- Host header
- SNI
- certificate validation path

Return edge and origin checks separately where possible:

```json
{
  "edge_status": "UP",
  "origin_status": "UP",
  "origin_check_method": "curl_resolve"
}
```

## 6. Improve HTTP Status Classification

Current `UP = 2xx or 3xx` is too narrow.

Add classification:

- `UP`: 2xx or 3xx
- `REACHABLE_PROTECTED`: 401 or 403
- `REACHABLE_NOT_FOUND`: 404
- `DEGRADED`: response received but slow, or unexpected 4xx depending config
- `DOWN`: timeout, connection refused, DNS failure, or 5xx
- `SSL_ERROR`: certificate invalid, expired, hostname mismatch, or TLS failure
- `UNKNOWN`: stale/missing check data

Avoid marking password-protected or WAF-protected sites as down just because they return 401/403.

## 7. Add HTTP Collector Guardrails

HTTP health checks must not become accidental monitoring DDoS.

Add:

- concurrency limit
- random jitter
- per-domain timeout
- HEAD first, GET fallback
- max response body size
- custom user-agent such as `BluePanda-Cockpit/1.0`
- per-account/domain exclusion list
- separate edge vs origin checks
- retry once before marking DOWN, where appropriate
- do not alert client-facing DOWN from one isolated failed check unless policy says so

## 8. Optimize Suspension Status Collection

Do not call WHM `accountsummary` individually for every account every 60 seconds if a cheaper source is available.

Preferred order:

1. Use WHM `listaccts` if it includes suspension status.
2. Later use WHM/cPanel hooks for suspend/unsuspend events.
3. Use per-account `accountsummary` only as fallback or for targeted refresh.

The 60-second freshness goal is good, but implement it cheaply.

## 9. Add Policy Failure Circuit Breaker

Add fields to policy engine action entries:

```toml
block_after_postcheck_failures = 1
require_manual_ack_after_failure = true
```

Rule:

If an action fails post-check for a target, the same action/target must not auto-run again until manually acknowledged or explicitly reset by policy.

Example:

If `RESTART_EXIM` fails post-check, do not keep restarting Exim every cycle.

## 10. Mandatory Auto-Run Notifications in Early Production

For the first production version:

- every auto-run must notify after execution
- failed auto-runs must notify immediately
- repeated auto-run failures must escalate to manual review

Do not allow silent auto-fixes until the system has proven reliability.

Update policy defaults:

```toml
notify_after = true
```

for all auto-run eligible actions.

## 11. Add Client API Response Discipline

Every client telemetry API response should include:

- `request_id`
- `server_id`
- `username`
- `cached_at`
- `collected_at`
- `expires_at`
- `freshness`
- `partial_data`
- `warnings`
- `data`

Example:

```json
{
  "request_id": "req_123",
  "server_id": "42",
  "username": "clientaccount",
  "cached_at": "2026-06-17T14:23:00Z",
  "collected_at": "2026-06-17T14:21:00Z",
  "expires_at": "2026-06-17T14:31:00Z",
  "freshness": "stale",
  "partial_data": true,
  "warnings": ["online_status_stale"],
  "data": {
    "account_status": "active",
    "online_status": "UNKNOWN"
  }
}
```

## 12. Add Future AI Client Context Endpoint

Add as future endpoint, not MVP blocker:

```text
GET /api/v1/account/client-context/{cpanel_username}
```

Purpose:

Return a sanitized, compact context block for the AI-assisted client area.

Example response:

```json
{
  "account": {
    "username": "clientaccount",
    "domain": "example.com",
    "plan_name": "Business",
    "status": "active"
  },
  "health": {
    "website_status": "UP",
    "ssl_status": "valid",
    "ssl_days_remaining": 74,
    "freshness": "fresh"
  },
  "usage": {
    "disk_percent": 21,
    "bandwidth_percent": 8
  },
  "client_safe_summary": "Your hosting account is active. Website is reachable. SSL is valid. Disk and bandwidth usage are within normal limits.",
  "support_recommendations": []
}
```

This endpoint must use the client-safe schema only.

## 13. Make Hybrid Deployment the Recommended MVP Topology

Update deployment recommendation:

```text
MVP recommended deployment:
- Control plane/dashboard/database/reporting on the dedicated experiment server.
- Lightweight collector/executor agent on the WHM production server.
- Communication over Tailscale/private network.
- WHM agent exposes no public HTTP.
```

Local-only on WHM should be allowed only for temporary dev/emergency use, not as the recommended MVP topology.

## 14. Keep Phase Boundaries Clear

Final phase classification:

```text
MVP-A: Internal Cockpit
- Phases 1–6

MVP-B: Client Area Read-Only Telemetry API
- Phase 2.5
- can be built in parallel only if it does not delay MVP-A

Post-MVP:
- Phase 7: Tier 1 Auto-Fix
- Phase 8: Telegram Approval Workflow
- Phase 9: Hardening and Operationalization
```

Phase 2.5 is strategically valid for BluePandaHosting’s AI-assisted client area, but it must remain read-only and client-safe.

## 15. Final Rule

Internal Cockpit can be powerful.

Client Area API must be boring.

Boring client-facing telemetry prevents support tickets.

Do not show clients internal drama unless they actually need to act on it.
