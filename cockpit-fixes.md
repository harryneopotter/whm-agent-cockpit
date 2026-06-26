I re-reviewed the current repo state on `main`. Static review only — I inspected the GitHub files/commit state, but did **not** run the test suite on the server.

Net verdict:

> **Much improved since the last review. Not production-safe yet. The skeleton is good, but the automation boundary still has a few dangerous/buggy seams.**

The latest commit explicitly fixes many of the previous findings: policy checks, executor audit/post-checks, DB env typo, `account_stats`, HTTP/SSL health, JetBackup parsing, client API fail-closed, and expanded disk mount checks.

## What is now fixed / better

The `COCKPIT_DB_PATH` typo is fixed in migrations. Good.

`WHMAccountsCollector` now populates `account_stats`, so the client telemetry API is no longer reading from a dead table.

The client telemetry API now fails closed if `COCKPIT_CLIENT_API_KEY` is unset, instead of allowing unauthenticated dev-mode access. Good correction.

The HTTP health collector now has concurrency, jitter, GET fallback after HEAD timeout, and real-ish SSL days extraction via socket.

The SSL collector now includes `valid_from`, `valid_to`, and pulls extra domains from `domain_mapping`, not only primary domains.

The critical loop now checks `/`, `/home`, `/var`, and `/tmp`, which is much more WHM-realistic. `/home` is the actual boss fight.

No `TODO`/`FIXME` hits showed up in the current code search. That does **not** mean complete, but it means the obvious placeholders were cleaned up.

## Remaining serious issues

### 1. Manual vs auto-run policy is still mixed

This is the biggest architecture issue.

In `PolicyEngine.evaluate()`, if an action is missing from policy or has `auto_run = false`, it returns:

```python
result["allowed"] = True
result["reason"] = "Approval required (auto_run=false)"
```

That makes sense for **manual dashboard actions**, but not for **automation**. The executor does not know whether the caller is manual, approved, or automated; it just sees `allowed=True` and proceeds.

Fix this before any automation:

```text
PolicyEngine.evaluate(action, target, mode="manual|auto")
```

For `mode="auto"`, `auto_run=false` must return `allowed=false`.

For `mode="manual"`, it can return `allowed=true` but should include `approval_required=true`.

Right now the policy wording says “approval required,” but the executor has no approval concept. That is a logic trap.

### 2. Consecutive detection matching is unreliable

The policy engine constructs issue IDs like:

```python
f"{action.action_id.lower()}_{target}"
```

But the critical loop creates issue IDs like:

```python
exim_stopped
litespeed_stopped
mail_queue_surge
disk_critical_home
```

So `RESTART_EXIM` with target `exim` would look for `restart_exim_exim`, while the real issue is `exim_stopped`.

Fix:

```text
Issue → recommended_action_id → target
```

Pass the actual `issue_id` into policy evaluation, or create an explicit mapping:

```toml
[actions.RESTART_EXIM]
related_issue_ids = ["exim_stopped"]
```

No string magic here. String magic is how bugs sneak in wearing slippers.

### 3. Cooldown timestamp parsing can break after first execution

Audit log timestamps use SQLite’s default:

```sql
datetime('now')
```

That produces a naive timestamp like:

```text
2026-06-20 15:42:00
```

But the policy engine compares it to an aware UTC datetime:

```python
now = datetime.now(timezone.utc)
elapsed = (now - last).total_seconds()
```

A naive-vs-aware subtraction can throw, causing `cooldown_passed = False`.

Practical result: after one successful action, future auto-runs for that action may get blocked forever because cooldown parsing keeps failing. Safe failure, yes. Correct behavior, no.

Fix by storing `created_at` as UTC ISO with timezone, or normalizing parsed timestamps:

```python
if last.tzinfo is None:
    last = last.replace(tzinfo=timezone.utc)
```

### 4. Circuit breaker fields exist but are not enforced

The policy has:

```python
block_after_postcheck_failures
require_manual_ack_after_failure
```

But `evaluate()` does not query `action_failed` events or manual acknowledgements. It only checks consecutive detection, cooldown, and rate limit.

This means a failed post-check is logged, but the policy engine does not yet use that failure to block future auto-runs.

That is a must-fix before Tier 1 auto-fix.

### 5. Rejected actions are still not audited

The executor now audits completed/failed/post-check-failed actions. Good.

But unknown action IDs, validation failures, and policy rejections return early before the audit step.

Your PRD explicitly wanted rejected attempts logged. This matters because rejected attempts are exactly where you catch bad Codex recommendations or future misuse.

Fix: audit every return path.

### 6. Post-check failure is double-logged

When a post-check fails, the executor writes `action_failed` inside the post-check block, then later writes another `action_failed` because the final status is still `post_check_failed`.

Not catastrophic, but it will pollute audit history and rate-limit/circuit-breaker logic.

Fix: only audit once per executor run.

### 7. LiteSpeed service name mismatch

Handler restarts:

```python
systemctl restart lsws
```

But post-check derives service name from action ID:

```python
RESTART_LITESPEED → litespeed
```

So it restarts `lsws`, then checks `litespeed`.

That can create false post-check failures.

Fix with an action metadata field:

```python
post_check_service="lsws"
display_service="LiteSpeed"
```

Also apply the same mapping to the service status collector. Service names should be config/catalog-driven, not inferred.

### 8. Client refresh worker does not actually refresh

The client API now has a background refresh worker, but it only logs and clears `_pending_refresh`. It does not trigger a collector, queue a job, or update data.

Also, single-account `GET /api/v1/account/stats/{username}` does **not** queue a refresh when stale; only batch does.

So this is better than before, but still misleading. Manual refresh says “queued,” but nothing targeted happens.

Fix options:

* Trigger `WHMAccountsCollector` for that username.
* Add a persistent `refresh_requests` table.
* Or honestly return `refresh_queued=false` until a real worker exists.

### 9. Client telemetry API still returns only basic stats

The API reads only from `account_stats` and returns disk, bandwidth, counts, plan, and PHP version. It does not join:

* `suspension_status`
* `account_health`
* `ssl_certs`

So it still does not return the client-area fields you actually want: active/suspended, website status, SSL status, SSL days remaining.

Also, `php_version` is exposed client-side. That may be okay, but decide deliberately. It was not part of the strict boring client-safe schema.

### 10. HTTP origin check still not actually implemented

The docstring says origin-specific checks are done “where applicable,” but the code only does direct `https://domain` edge checks and SSL socket checks. `origin_status` and `origin_check_method` remain initialized but unused.

This is not a blocker for internal monitoring, but do not claim SNI-safe origin checks are implemented yet.

### 11. Deployment privilege model is not ready for actions

The systemd services run as the unprivileged `cockpit` user with `NoNewPrivileges=true` and no capabilities.

That is good for dashboard/API safety, but restart handlers use `systemctl restart ...`, which will not work from that unprivileged context without a sudoers/helper design.

You need the promised deterministic helper layer:

```text
cockpit-executor user
↓
sudoers allowlist
↓
specific scripts only
```

Right now the safety model is conceptually present, but action execution privilege plumbing is not.

### 12. WHM auth client should be cleaned up

`WHMClient` sets both `httpx.BasicAuth("root", token)` and an `Authorization: whm root:TOKEN` header.

For WHM API tokens, use the WHM token header only. Mixing BasicAuth and custom `Authorization` risks one overwriting the other depending on how `httpx` applies auth.

Also, `verify=False` is okay for localhost/self-signed WHM during dev, but for remote/Tailscale control plane usage it should be configurable.

## Current stage rating

### Good enough for

* Local/dev dashboard skeleton
* Read-only collector experiments
* SQLite schema testing
* WHM account pull testing
* UI shape validation
* Client area API shape testing with fake/controlled data

### Not good enough for

* Production auto-fix
* Real Codex-triggered executor actions
* Client-facing health confidence
* “Restart service safely” buttons without privilege/helper redesign
* Backup SLA visibility

## Priority fix order for Codex

Give Codex this order. No wandering. No “while I was there I rebuilt the dashboard” nonsense.

1. Split executor calls into `mode=manual` and `mode=auto`.
2. Audit every rejected action path.
3. Fix audit timestamp timezone handling.
4. Enforce `block_after_postcheck_failures`.
5. Replace action→issue string guessing with explicit issue/action mapping.
6. Fix LiteSpeed `lsws`/`litespeed` service mapping.
7. Make client API join `account_stats + suspension_status + account_health + ssl_certs`.
8. Replace fake refresh queue with real persistent refresh requests or remove the claim.
9. Implement actual origin check or remove `origin_status` from current output.
10. Add sudoers/helper design for deterministic action scripts.

## Final verdict

This is now a **credible MVP codebase**, not just a generated PRD cosplay.

But the dangerous part is still exactly where expected:

> the boundary between “observing” and “acting.”

Keep Tier 1 auto-fix disabled until the policy/executor/audit/privilege path is fixed. The read-only dashboard and collectors can move forward; the robot-hand-on-root-buttons part still needs adult supervision.
