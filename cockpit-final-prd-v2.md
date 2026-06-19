Cockpit System — Final PRD and Implementation Plan

1. Product Name

Cockpit

Internal WHM/cPanel hosting operations cockpit with supervised maintenance automation.

---

2. One-Line Summary

Cockpit is a production-safe internal hosting operations system that monitors WHM/cPanel servers, shows clear operational status, supports safe manual actions, generates scheduled health reports, and allows Codex to recommend only predefined deterministic actions through a strict action catalog.

---

3. Core Purpose

Cockpit exists to answer four operational questions quickly:

1. What is broken or risky right now?
2. Who or what is affected?
3. What safe action can be taken immediately?
4. When should the operator escalate to WHM/manual handling?

It is not a WHM replacement.

It is a first-response operations cockpit.

---

4. Target Environment

Initial production target:

- WHM/cPanel server
- CloudLinux
- LiteSpeed Enterprise
- JetBackup installed and configured
- Imunify360
- MariaDB
- Exim/Dovecot
- DNS service: named / PowerDNS depending on server config
- Hetzner dedicated server
- Production hosting workloads
- Codex installed for assisted routine ops review

---

5. Product Separation

Cockpit must be treated as two separate but connected systems.

---

Product A: Cockpit Dashboard

5.1 Purpose

The Cockpit Dashboard is the human-facing UI.

It provides:

- server visibility
- account/domain search
- health summaries
- backup status
- mail diagnostics
- SSL/DNS diagnostics
- resource offender detection
- safe manual action buttons
- WHM deep links
- report viewer
- audit log viewer
- pending approval view
- missing-action request view

The dashboard is the operator’s visual control plane.

---

5.2 Dashboard Responsibilities

The dashboard is responsible for:

- showing current system state
- showing stale/unknown data clearly
- allowing manual safe actions from the action catalog
- showing action results
- showing Codex recommendations
- showing automation history
- showing pending approvals
- linking to WHM/cPanel/JetBackup/LiteSpeed/Imunify when out of scope

---

5.3 Dashboard Non-Responsibilities

The dashboard must not:

- execute arbitrary shell commands
- allow arbitrary script execution
- replace WHM/cPanel
- perform dangerous remediation directly
- restore accounts in MVP
- restart MariaDB in MVP
- reboot the server in MVP
- terminate/suspend/unsuspend accounts in MVP
- modify DNS records in MVP
- perform mass WordPress/plugin updates
- expose root-level controls casually

---

Product B: Maintenance Agent

5.4 Purpose

The Maintenance Agent is the background automation and reporting layer.

It runs collectors, generates structured reports, detects issues, applies deterministic rules, lets Codex review structured reports, and triggers only predefined actions through the executor.

---

5.5 Maintenance Agent Responsibilities

The Maintenance Agent is responsible for:

- scheduled collectors
- immediate critical monitoring loop
- 12-hour operational reports
- alert severity classification
- Codex review pipeline
- policy engine decisions
- deterministic action execution
- post-action verification
- Telegram notifications
- approval request workflow
- missing-action logging
- auto-fix history
- system self-monitoring

---

5.6 Maintenance Agent Non-Responsibilities

The Maintenance Agent must not:

- give Codex shell access
- let Codex generate scripts
- let Codex execute commands
- accept generic "RUN_COMMAND"
- accept arbitrary "RUN_SCRIPT"
- auto-create new action buttons
- bypass policy checks
- auto-run dangerous actions

---

Shared Layer: Action Catalog and Executor

6.1 Core Principle

The AI can reason.

The AI can recommend.

The AI can select from approved buttons.

The AI cannot invent buttons.

The AI cannot run shell commands.

The AI cannot modify the button catalog.

---

6.2 Action Catalog

The Action Catalog is the central contract for all allowed actions.

Every action must define:

- "action_id"
- description
- risk tier
- target type
- allowed arguments
- input validation rules
- approval requirement
- cooldown
- rate limit
- timeout
- mutex/lock key
- pre-checks
- exact script/API handler
- post-checks
- rollback notes
- audit fields
- dry-run behavior

There must be no generic actions such as:

- "RUN_COMMAND"
- "EXEC_SHELL"
- "CUSTOM_BASH"
- "AI_GENERATED_SCRIPT"
- arbitrary "RUN_SCRIPT"

All action names must be specific.

Examples:

- "CHECK_SSL_FOR_DOMAIN"
- "RUN_AUTOSSL_FOR_DOMAIN"
- "RESTART_EXIM"
- "RESTART_DOVECOT"
- "RESTART_LITESPEED"
- "CHECK_BACKUP_FOR_ACCOUNT"
- "CLEAR_LSCACHE_FOR_ACCOUNT"
- "GET_TOP_DISK_USERS"
- "CHECK_MAIL_HEALTH_FOR_DOMAIN"

---

6.3 Executor

The executor is the only component allowed to perform actions.

It must:

- accept only known "action_id"s
- validate all targets and arguments
- reject unknown actions
- enforce risk tier rules
- enforce approval rules
- enforce cooldowns
- enforce rate limits
- prevent duplicate concurrent actions
- run only hardcoded scripts/API handlers
- log every attempt
- log rejected attempts
- run post-checks
- return structured results

The executor must support:

- "dry_run"
- "execute"

Dry-run must show:

- target validation result
- exact action that would run
- risk tier
- approval requirement
- pre-check status
- expected post-check

---

7. Codex Role

Codex is a reviewer and reasoning layer only.

7.1 Codex Input

Codex receives structured reports, not raw server freedom.

Input should include:

- current alerts
- server health
- backup health
- mail status
- SSL warnings
- resource offenders
- issue state
- available action catalog IDs
- previous failed actions
- missing action history

---

7.2 Codex Output

Codex may return:

- summary
- issue prioritization
- likely cause
- recommended existing "action_id"
- target
- confidence
- reason
- approval recommendation
- missing-action request

Example valid output:

{
  "issue_id": "ssl_expiring_example_com",
  "recommended_action_id": "RUN_AUTOSSL_FOR_DOMAIN",
  "target": {
    "domain": "example.com"
  },
  "confidence": "high",
  "reason": "SSL expires in 4 days and AutoSSL is an approved Tier 1 action."
}

---

7.3 Forbidden Codex Output

Codex must not output:

- shell commands
- bash snippets
- custom scripts
- package install commands
- file modification instructions
- direct remediation outside action catalog
- arbitrary server operations

If Codex identifies a needed action that does not exist, it must create a missing-action request.

---

7.4 Codex Input Schema

Codex receives a structured JSON report. All fields are required unless marked optional.

{
  "report_id": "report-20260617-140000",
  "generated_at": "2026-06-17T14:00:00Z",
  "server": {
    "hostname": "hetzner-prod-1",
    "load_avg_1m": 1.2,
    "load_avg_5m": 0.9,
    "load_avg_15m": 0.8,
    "cpu_percent": 45,
    "ram_used_percent": 67,
    "swap_used_percent": 12,
    "uptime_seconds": 1234567
  },
  "disk": {
    "used_percent": 71,
    "inode_used_percent": 34,
    "free_gb": 120
  },
  "services": [
    {"name": "litespeed", "status": "running"},
    {"name": "exim", "status": "stopped"},
    {"name": "dovecot", "status": "running"},
    {"name": "mariadb", "status": "running"},
    {"name": "named", "status": "running"}
  ],
  "mail": {
    "queue_size": 847,
    "frozen_count": 23,
    "exim_errors_last_hour": 45
  },
  "backups": {
    "destination_reachable": true,
    "last_run_at": "2026-06-17T02:00:00Z",
    "failed_accounts": ["client5"],
    "accounts_missing_recent_backup": ["client5", "client12"],
    "missing_backup_threshold_hours": 26
  },
  "ssl": {
    "expiring_within_14_days": [
      {"domain": "example.com", "days_remaining": 4},
      {"domain": "another.com", "days_remaining": 11}
    ]
  },
  "alerts": [
    {
      "issue_id": "exim_stopped_001",
      "severity": "critical",
      "state": "NEW",
      "detected_at": "2026-06-17T13:47:00Z",
      "consecutive_detections": 3,
      "description": "Exim mail service is not running"
    }
  ],
  "available_action_ids": [
    "RESTART_EXIM",
    "RESTART_DOVECOT",
    "RESTART_LITESPEED",
    "RUN_AUTOSSL_FOR_DOMAIN",
    "CHECK_SSL_FOR_DOMAIN",
    "CHECK_MAIL_HEALTH_FOR_DOMAIN",
    "REFRESH_BACKUP_STATUS",
    "CLEAR_LSCACHE_FOR_ACCOUNT",
    "GET_TOP_DISK_USERS"
  ],
  "previous_failed_actions": [
    {
      "action_id": "RESTART_EXIM",
      "attempted_at": "2026-06-17T13:30:00Z",
      "result": "post_check_failed",
      "attempts_in_24h": 2
    }
  ],
  "missing_action_history": [
    {
      "pattern": "backup_job_failed_for_account",
      "logged_count": 3,
      "first_logged_at": "2026-06-15T02:00:00Z"
    }
  ]
}

---

7.5 Codex Output Schema

Codex returns a structured JSON object.

The top-level object must always be present.

recommendations must always be an array, even if empty.

If no issues are detected, summary must confirm the clean state and recommendations must be an empty array.

{
  "reviewed_at": "2026-06-17T14:00:45Z",
  "report_id": "report-20260617-140000",
  "summary": "Critical: Exim is stopped with two failed restart attempts in the last 24 hours. Mail queue is elevated at 847 messages with 23 frozen. Two SSL certificates expiring within 14 days. Two accounts are missing recent backups.",
  "recommendations": [
    {
      "issue_id": "exim_stopped_001",
      "priority": 1,
      "likely_cause": "Exim stopped unexpectedly. Two previous restart attempts failed post-check, suggesting a config issue or resource constraint rather than a transient stop.",
      "recommended_action_id": "RESTART_EXIM",
      "target": {},
      "confidence": "medium",
      "reason": "Service must be restarted. Confidence is medium due to prior post-check failures. Operator should review Exim error logs if this attempt also fails.",
      "approval_recommendation": "auto_run_with_notification"
    },
    {
      "issue_id": "ssl_expiring_example_com",
      "priority": 2,
      "likely_cause": "AutoSSL has not renewed the certificate within the expected window.",
      "recommended_action_id": "RUN_AUTOSSL_FOR_DOMAIN",
      "target": {"domain": "example.com"},
      "confidence": "high",
      "reason": "SSL expires in 4 days. AutoSSL renewal is a safe, deterministic action with no downside risk.",
      "approval_recommendation": "auto_run"
    },
    {
      "issue_id": "backup_missing_client5",
      "priority": 3,
      "likely_cause": "client5 has no recent backup and a recorded backup failure. Cause is unknown without further investigation.",
      "recommended_action_id": null,
      "target": {"account": "client5"},
      "confidence": "low",
      "reason": "No catalog action covers backup failure diagnosis. Manual JetBackup review required.",
      "approval_recommendation": "manual_only",
      "missing_action_request": {
        "pattern": "backup_job_failed_for_account",
        "suggested_action_name": "INVESTIGATE_BACKUP_FAILURE_FOR_ACCOUNT",
        "why_insufficient": "Current catalog has no action to diagnose why a specific account backup failed.",
        "proposed_target_type": "account",
        "risk_level": "low",
        "proposed_validation": "account must exist in WHM",
        "automation_eligibility": "read_only"
      }
    }
  ]
}

Valid approval_recommendation values:

- "auto_run": policy engine may run without notification
- "auto_run_with_notification": policy engine may run but must notify before or after
- "approval_required": must not run without explicit operator approval
- "manual_only": no automation path, operator must act directly
- null: no action recommended

---

8. Missing-Action Queue

When the system detects a recurring issue that cannot be safely handled, Codex or the rule engine may log a missing-action request.

A missing-action request should include:

- issue pattern
- suggested new action name
- why current actions are insufficient
- proposed target type
- risk level
- proposed validation
- whether it should be read-only, manual-only, approval-required, or auto-fixable later

New actions must go through a promotion process:

1. Missing action requested
2. Operator reviews
3. Deterministic script/API handler written manually
4. Dry-run tested
5. Post-check added
6. Added to action catalog
7. Manual-only for first N successful uses
8. Eligible for automation later only after proven safe

No new button goes straight to auto-fix.

---

8.5 Policy Engine

The policy engine controls whether a Codex-recommended or rule-triggered action is allowed to auto-run, requires approval, or must be blocked.

---

Format:

The policy engine is a TOML configuration file.

It is:

- stored at a defined path on the server
- readable by the Maintenance Agent at runtime
- version-controlled in git
- not writable by any automated process
- not modifiable by Codex
- only modifiable by the operator

---

Schema per action entry:

[actions.RESTART_EXIM]
auto_run = true
require_consecutive_detections = 2
cooldown_seconds = 300
max_per_24h = 5
notify_before = false
notify_after = true
enabled = true

[actions.RUN_AUTOSSL_FOR_DOMAIN]
auto_run = true
require_consecutive_detections = 1
cooldown_seconds = 3600
max_per_24h = 10
notify_before = false
notify_after = true
enabled = true

[actions.RESTART_MARIADB]
auto_run = false
require_consecutive_detections = 1
cooldown_seconds = 600
max_per_24h = 2
notify_before = true
notify_after = true
enabled = false

---

Field definitions:

- auto_run: whether this action can execute without operator approval
- require_consecutive_detections: minimum consecutive detections of the triggering issue before auto-run is eligible
- cooldown_seconds: minimum seconds between executions of this action for the same target
- max_per_24h: maximum allowed executions in any rolling 24-hour window
- notify_before: send Telegram notification before executing
- notify_after: send result notification after executing
- block_after_postcheck_failures: number of consecutive post-check failures before this action/target is blocked from auto-run
- require_manual_ack_after_failure: if true, action/target requires manual operator acknowledgment before auto-run resumes after a failure
- enabled: global kill switch for this action in the policy; false blocks all automation for this action

**Default for early production**: Every auto-run must notify after execution (`notify_after = true` for all auto-run-eligible actions). Failed auto-runs must notify immediately. Repeated failures escalate to manual review.

---

Decision logic:

When the Maintenance Agent evaluates a Codex recommendation or rule trigger, the policy engine checks in this order:

1. Is the action enabled in policy?
2. Is auto_run true?
3. Have require_consecutive_detections been met?
4. Has the cooldown passed for this action and this target?
5. Is max_per_24h not yet reached?
6. Do executor pre-checks pass?

All six must be true for auto-run.

If any check fails, the action is either queued for approval or blocked, depending on which check failed.

---

Failure behavior:

- enabled = false: block silently, write to audit log
- auto_run = false: queue for operator approval, notify via Telegram
- consecutive detections not met: monitor only, take no action
- cooldown active: skip this cycle, log next eligible time
- max_per_24h reached: block, send warning notification
- pre-check failed: block, escalate per escalation rules

---

Audit requirement:

Every policy engine decision must be logged with:

- action_id
- policy version (git commit hash of policy file at time of decision)
- result of each condition check
- final decision
- timestamp

---

Fallback:

If the policy file cannot be loaded, all auto_run decisions default to false.

No action runs automatically if the policy engine is unavailable.

Monitoring and alerting continue regardless of policy engine state.

---

9. Monitoring Model

Cockpit uses two monitoring cycles.

---

9.1 Immediate Critical Loop

Runs every 1–5 minutes.

Used for:

- LiteSpeed down
- Exim down
- Dovecot down
- DNS down
- disk critical
- inode critical
- RAID/storage issue
- backup destination unreachable
- account missing recent backup beyond configured threshold
- mail queue surge
- server load runaway
- MariaDB down
- Cockpit collector failure
- Telegram/reporting failure

---

9.2 12-Hour Operational Report

Runs twice daily.

Used for:

- overall health summary
- backup review
- SSL expiry review
- account resource warnings
- LVE fault trends
- mail health summary
- disk/inode trends
- JetBackup health
- Imunify summary
- auto-fix summary
- unresolved issues
- missing-action requests
- “all okay” confirmation

The system must send an “all okay” report when healthy so silence is not confused with system failure.

---

10. Issue Lifecycle

Every detected issue must have a state.

Required states:

- "NEW"
- "ACKNOWLEDGED"
- "AUTO_FIX_ELIGIBLE"
- "PENDING_APPROVAL"
- "FIX_RUNNING"
- "POST_CHECK_RUNNING"
- "RESOLVED"
- "FAILED"
- "ESCALATED_TO_WHM"
- "SUPPRESSED"

This prevents duplicate alerts, repeated fixes, and confusing automation loops.

---

11. Data Freshness and Stale Data

Every collected metric must include:

- "collected_at"
- "ttl_seconds"
- freshness status:
  - "fresh"
  - "stale"
  - "unknown"

Stale important data must become an alert.

Examples:

- JetBackup status stale for 9 hours → warning
- Exim queue collector failed repeatedly → warning
- server health collector dead → critical

The dashboard must never show old green data as if it is current.

---

12. Core Dashboard Views

12.1 Global Dashboard

Shows:

- overall status
- server load
- CPU/RAM/swap
- disk usage
- inode usage
- service status
- mail queue
- backup health
- SSL expiry count
- critical alerts
- warnings
- stale collectors
- last 12-hour report status
- auto-fix history
- WHM shortcut buttons

---

12.2 Account Search

Search by:

- cPanel username
- primary domain
- addon domain
- parked/alias domain
- subdomain where feasible

Account page shows:

- username
- primary domain
- package
- disk usage
- inode usage
- PHP version
- SSL status
- JetBackup status
- restore point count
- mailbox quota warnings
- recent PHP errors
- LVE/resource faults
- Imunify status where available
- WHM/cPanel/JetBackup deep links
- safe actions

---

12.3 Domain Diagnostics

For a domain, show:

- local account mapping
- DNS resolution
- authoritative nameservers
- HTTP status
- HTTPS status
- SSL expiry
- AutoSSL status
- MX records
- SPF
- DKIM
- DMARC
- reverse DNS where relevant
- likely issue summary
- suggested safe action

---

12.4 Mail Health

Show:

- Exim status
- Dovecot status
- queue size
- frozen mail count
- top senders
- recent Exim errors
- mailbox quota warnings
- server IP blacklist checks where feasible
- WHM Mail Queue link

---

12.5 Backup Health

Show:

- JetBackup service status
- latest backup run
- failed accounts
- skipped accounts
- accounts without recent backups
- restore points per account
- backup destination status
- sudden backup size drops/spikes
- backup age warnings
- restore-readiness score

Backup visibility must answer:

«Can this account be restored today if needed?»

Not just:

«Did a backup job run?»

---

12.6 Resource Offenders

Show:

- top disk users
- top inode users
- top CPU/LVE offenders
- high I/O accounts
- repeated entry process faults
- large error logs
- large mailboxes
- sudden resource growth

---

12.7 Audit Log

Must show:

- issue detected
- collector result
- Codex recommendation
- policy decision
- approval request
- approval response
- action executed
- rejected actions
- script/API handler used
- arguments
- stdout/stderr
- post-check result
- notification result

Audit logs should be append-only where practical.

---

13. WHM Deep Links

Cockpit must include deep links instead of recreating WHM.

Global shortcuts:

- Login to WHM
- List Accounts
- Service Manager
- Mail Queue Manager
- AutoSSL
- JetBackup
- Imunify360
- CloudLinux Manager
- LiteSpeed WebAdmin
- Backup Configuration
- SSL/TLS Status

Account-level shortcuts:

- Open account in WHM
- Login to cPanel as user
- Open JetBackup for account
- Open Email Accounts
- Open Zone Editor
- Open SSL/TLS Status
- Open MultiPHP Manager
- Open File Manager
- Open Imunify scan/results

The dashboard must not store WHM root password.

---

14. Action Risk Tiers

Tier 0: Read-Only

Always allowed after login.

Examples:

- check service status
- check DNS
- check SSL
- check backup availability
- check mail health
- show top disk users

---

Tier 1: Low-Risk Auto-Fix Eligible

May be auto-run only when deterministic rules, policy, validation, cooldowns, and post-checks pass.

Examples:

- run AutoSSL for expiring domain
- restart LiteSpeed if stopped
- restart Exim if stopped
- restart Dovecot if stopped
- restart DNS service if stopped
- refresh JetBackup status
- clear LSCache for a clearly scoped account/domain

Codex recommendation alone is never enough authorization.

---

Tier 2: Approval Required

May be suggested but requires explicit operator approval.

Examples:

- restart MariaDB
- restart cPanel service stack
- kill abusive process
- clear large logs
- suspend outgoing mail for suspected compromised account
- malware cleanup
- quota/package adjustment
- selected backup restore

Most Tier 2 actions should not be implemented in MVP.

---

Tier 3: Manual Only

No automation in MVP.

Examples:

- reboot server
- full account restore
- terminate account
- suspend/unsuspend account
- mass delete files
- mass WordPress updates
- destructive mail queue cleanup
- billing changes
- DNS record edits

Cockpit should show a report and a WHM link.

---

15. Security Requirements

Mandatory:

- no public unauthenticated exposure
- prefer Tailscale or Cloudflare Access
- HTTPS if exposed beyond localhost
- authentication required
- CSRF protection
- strict input validation
- no WHM root password storage
- least privilege
- allowlisted commands only
- no generic shell endpoint
- all actions audited
- rejected actions audited
- secrets stored in root-owned config/env files
- Telegram action buttons must be signed and expiring
- action arguments must be validated against known accounts/domains
- action catalog must not be writable by Codex process

---

16. Privilege Separation

Recommended process roles:

cockpit-ui

- serves dashboard
- reads database
- requests actions through backend
- no sudo
- no direct shell action access

cockpit-collector

- runs read-only collectors
- uses read-only WHM/API token where possible
- writes telemetry
- no remediation permission

cockpit-executor

- runs approved action handlers only
- uses sudoers allowlist where shell access is needed
- cannot accept arbitrary command text
- logs all results

codex-review

- reads structured reports
- writes recommendations
- cannot execute actions
- cannot modify action catalog
- cannot modify scripts

The process that talks to Codex must not be the same unrestricted process that executes actions.

---

17. Deployment Topology

Deployment topology must be decided before implementation.

Option A: Local-only on WHM server

Pros:

- simple
- direct access to data
- easier collectors

Cons:

- larger production attack surface

Allowed for MVP only if:

- bound to localhost/Tailscale/private IP
- authenticated
- locked down
- no public exposure

---

Option B: Separate Control VM

Pros:

- better isolation
- less production UI exposure

Cons:

- more moving parts
- requires SSH/API collectors

---

Option C: Hybrid (Recommended MVP Topology)

- lightweight collectors/executor agent on WHM server
- control plane/dashboard/database/reporting on a dedicated server
- communication over Tailscale or private network
- WHM agent exposes no public HTTP

Best balance of safety and practicality.

Allowed for MVP only.

Local-only on WHM (Option A) is allowed only for temporary dev/emergency use, not as the recommended MVP topology.

---

18. Emergency Controls

Cockpit must include emergency controls:

- "PAUSE_ALL_AUTOFIX"
- "PAUSE_TELEGRAM_ACTIONS"
- "PAUSE_CODEX_REVIEW"
- "READ_ONLY_MODE"

Monitoring should continue even when automation is paused.

---

19. Escalation Rules

Examples:

- if Tier 1 action fails once → notify
- if post-check fails → mark failed
- if same issue repeats 3 times in 24h → require manual review
- if service restart fails → escalate to WHM/manual
- if disk critical and no safe cleanup exists → Telegram critical + WHM link
- if collector stale beyond threshold → alert
- if report not generated on time → alert

No endless fix loops.

---

20. Backup Restore-Readiness

JetBackup module must eventually score restore readiness.

Factors:

- latest backup age
- restore point count
- skipped/failed account status
- destination reachability
- sudden backup size drop/spike
- account-specific restore point availability
- periodic sample restore test later, preferably off-production

MVP should not perform restores.

MVP should show whether a restore looks possible.

---

21. Account/Domain Mapping Strategy

Cockpit must maintain a domain/account cache.

Sources:

- WHM account list
- cPanel userdata
- addon domains
- parked/alias domains
- subdomains
- DNS zones
- AutoSSL domain list

Cache must refresh:

- on schedule
- after account creation
- after account removal
- after package/domain change
- after addon domain changes
- when manual refresh is triggered

Search must clearly show when mapping data is stale.

---

22. Self-Monitoring

Cockpit must monitor itself.

Alerts for:

- collector scheduler stopped
- report not generated
- Telegram delivery failed
- database write failed
- executor unavailable
- action catalog failed to load
- Codex review failed
- Cockpit DB/log disk usage high
- stale telemetry
- failed backup of Cockpit data/config

---

23. MVP Non-Goals

Do not build in MVP:

- WHM replacement
- cPanel replacement
- client portal
- ticket system
- billing system
- public multi-tenant SaaS
- autonomous AI sysadmin
- arbitrary command runner
- full backup manager
- restore manager
- full mail queue manager
- WordPress management suite
- mass updater
- destructive cleanup engine

---

24. Implementation Plan

Phase 1: Read-Only Collectors

Goal:

Build reliable data collection before any UI/actions.

Collectors:

- server health
- CPU/load/RAM/swap
- disk usage
- inode usage
- uptime
- RAID/storage status
- service status
- JetBackup status
- mail queue
- SSL expiry
- WHM account list
- CloudLinux/LVE stats
- Imunify summary
- account/domain mapping

Requirements:

- structured JSON output
- timestamps
- TTL/freshness status
- collector error logging
- no remediation actions
- SQLite storage
- 7–30 day telemetry retention

Deliverable:

- backend collectors
- database schema
- freshness tracking
- collector failure alerts

---

Phase 2: Read-Only Dashboard

Goal:

Show current state safely.

Pages:

- global dashboard
- account search
- domain diagnostics
- mail health
- backup health
- resource offenders
- WHM links
- audit log placeholder

Requirements:

- authentication
- mobile-friendly layout
- stale data indicators
- no action buttons yet
- WHM deep links
- basic role separation

Deliverable:

- usable read-only Cockpit UI

---

Phase 2.5: Client Area Read-Only Telemetry API

Goal:

Provide a read-only stats API for the custom Next.js client area to display per-account operational status.

---

Context:

The client area is a custom Next.js application that uses the WHMCS API for client and service management.

When a client logs in, the flow is:

1. Next.js queries WHMCS GetClientsProducts with the authenticated client's ID.
2. WHMCS returns the list of cPanel accounts belonging to that client, including cpanel_username, domain, and serverid per service.
3. Next.js queries the Cockpit stats API for each account.
4. Client area renders per-account stats with stale-while-revalidate behavior.

---

Authorization model:

- Server-to-server shared API key between the Next.js server and the Cockpit.
- WHMCS is the access control boundary. GetClientsProducts guarantees account ownership — WHMCS only returns accounts belonging to the authenticated client.
- The Cockpit stats API is authorization-agnostic. It returns stats for any valid cPanel username when queried with the correct API key. It does not need to know which client owns which account.
- The shared API key must never be exposed to the browser. All Cockpit API calls must be server-side only, in Next.js API Routes or Server Components.
- WHMCS GetClientsProducts stats fields (disk, bandwidth) are only as fresh as WHMCS's last sync cycle (up to 24 hours). Do not use them for the stats display. Use Cockpit API data only. WHMCS response is used for username, domain, serverid, and plan name only.

---

New collectors required:

Account Stats Collector

- Source: WHM API accountsummary per account
- Schedule: every 10 minutes
- Fields: disk_used_mb, disk_limit_mb, bandwidth_used_mb, bandwidth_limit_mb, email_count, db_count, subdomain_count, addon_domain_count, parked_domain_count, ftp_count, plan_name, primary_ip, php_version
- Storage: account_stats table in SQLite with collected_at timestamp

Suspension Status Collector

- Source: WHM API `listaccts` (includes suspension status; avoid per-account calls)
- Schedule: every 60 seconds
- Must be a separate fast-path query independent of the full account stats collector
- Storage: separate suspension_status table to allow short-TTL refresh without triggering a full stats fetch
- Future optimization: WHM/cPanel hooks for suspend/unsuspend events
- Fallback: per-account `accountsummary` only for targeted refresh or if listaccts lacks suspension data

HTTP Health Collector

- Source: outbound HEAD/GET to https://{primary_domain}/ from the WHM server
- Schedule: every 3 minutes per account
- Records: http_status_code, response_time_ms, ssl_valid, ssl_days_remaining
- Classification:
  - UP: 2xx or 3xx response received
  - DEGRADED: response received but response_time_ms above 5000
  - DOWN: timeout, connection refused, or 5xx
  - SSL_EXPIRING: valid cert but expires within 14 days
  - SSL_EXPIRED: cert invalid or expired
- Storage: account_health table with collected_at timestamp
- Staleness rule: if collected_at is older than 5 minutes, online_status must be returned as UNKNOWN regardless of last known state. Never return stale UP or stale DOWN after this threshold.
- DNS/proxy caveat: health check is outbound from the WHM server. If the domain uses Cloudflare proxy or external DNS, the check reflects the edge, not the origin. For origin-specific checks, use curl --resolve: `curl --resolve example.com:443:SERVER_IP https://example.com/`. This preserves hostname, Host header, SNI, and certificate validation. Return edge and origin checks separately: `{"edge_status": "UP", "origin_status": "UP", "origin_check_method": "curl_resolve"}`.
- HTTP collector guardrails: concurrency limit (max 50 parallel checks), random jitter (±30s), per-domain timeout (15s), HEAD first with GET fallback, max response body size (10KB), custom user-agent `BluePanda-Cockpit/1.0`, per-account/domain exclusion list, retry once before marking DOWN.
- Classification:
  - UP: 2xx or 3xx response received
  - REACHABLE_PROTECTED: 401 or 403 (password/WAF-protected, not DOWN)
  - REACHABLE_NOT_FOUND: 404
  - DEGRADED: response received but response_time_ms above 5000
  - DOWN: timeout, connection refused, DNS failure, or 5xx
  - SSL_ERROR: certificate invalid, expired, hostname mismatch, or TLS failure
  - SSL_EXPIRING: valid cert but expires within 14 days
  - SSL_EXPIRED: cert invalid or expired
  - UNKNOWN: stale/missing check data

---

API Endpoints:

Single account stats:

GET /api/v1/account/stats/{cpanel_username}
Header: X-API-Key: {shared_secret}

Response:

{
  "request_id": "req_123",
  "server_id": "42",
  "username": "clientaccount",
  "cached_at": "2026-06-17T14:23:00Z",
  "collected_at": "2026-06-17T14:21:00Z",
  "expires_at": "2026-06-17T14:31:00Z",
  "freshness": "fresh",
  "partial_data": false,
  "warnings": [],
  "data": {
    "disk_used_mb": 4200,
    "disk_limit_mb": 20480,
    "bandwidth_used_mb": 8100,
    "bandwidth_limit_mb": 102400,
    "email_count": 12,
    "db_count": 4,
    "subdomain_count": 3,
    "addon_domain_count": 1,
    "parked_domain_count": 0,
    "plan_name": "Business",
    "account_status": "active",
    "account_status_checked_at": "2026-06-17T14:24:00Z",
    "php_version": "8.2",
    "online_status": "UP",
    "online_status_checked_at": "2026-06-17T14:21:00Z",
    "online_response_time_ms": 342,
    "ssl_valid": true,
    "ssl_days_remaining": 74
  }
}

Batch account stats:

POST /api/v1/account/stats/batch
Header: X-API-Key: {shared_secret}
Body: {"usernames": ["account1", "account2", "account3"]}

Response:

{
  "results": {
    "account1": { "cached_at": "...", "freshness": "fresh", "data": {...} },
    "account2": { "cached_at": "...", "freshness": "stale", "data": {...} },
    "account3": { "cached_at": "...", "freshness": "unknown", "data": null }
  }
}

Batch handler must use a single SQLite IN query for cache hits. 

**Cache-first behavior**: If cached data is stale or missing, return stale/unknown data immediately and enqueue a refresh job for the next cycle. Do not block the client response on expensive WHM API or HTTP checks. Manual refresh endpoint may request immediate refresh but respects rate limits.

Parallel fetching: cache misses for the batch response are served from cache (even if stale) — the refresh is background-only.

Manual refresh:

POST /api/v1/account/stats/{cpanel_username}/refresh
Header: X-API-Key: {shared_secret}
Rate limit: once per 5 minutes per account.
Forces fresh fetch from WHM API and HTTP health check, bypassing cache TTL.

---

Caching and freshness rules:

- account_stats (disk, bandwidth, counts): 10-minute TTL
- account_status (suspended/active): 60-second TTL
- online_status (HTTP health check): 3-minute TTL
- After 5 minutes without a fresh online_status check: return UNKNOWN, not last known state
- Every API response must include cached_at and freshness fields

---

Stale data behavior in Next.js client area:

The Next.js client area must use stale-while-revalidate (SWR or equivalent).

Rules:

- Show stale cached data immediately while revalidating in background.
- Display "Last updated X minutes ago • Refreshing..." when showing stale data.
- After 10 minutes of failed refreshes: display "Last updated X minutes ago — unable to refresh."
- For online_status: after 5 minutes of staleness, show "Status unknown" not the last known UP or DOWN.
- For account_status: TTL is 60 seconds. Treat as near-real-time. A suspended account should never display as Active for more than 60 seconds.

---

Future multi-server routing:

WHMCS GetClientsProducts returns a serverid per service.

The Next.js server must maintain a routing map of serverid to Cockpit URL:

COCKPIT_SERVERS = {
  "42": "https://cockpit.server1.example.com"
}

Build this routing layer now even if only one entry exists. Adding a second server requires only one config line change.

---

Deliverable:

- account_stats, suspension_status, and account_health tables in SQLite
- Account stats collector (10-minute schedule)
- Suspension status collector (60-second schedule)
- HTTP health collector (3-minute schedule) with UNKNOWN threshold logic
- GET /api/v1/account/stats/{username}
- POST /api/v1/account/stats/batch with parallel cache-miss fetching
- POST /api/v1/account/stats/{username}/refresh with rate limiting
- cached_at and freshness fields in every response
- **Client-safe schema only** — no internal operator data (LVE, error logs, Imunify findings, action history, Codex recommendations). See client-safe schema in addendum §2.

Future endpoint (not MVP blocker):

GET /api/v1/account/client-context/{cpanel_username}

Returns a sanitized, compact context block for AI-assisted client area. See addendum §12 for schema.

---

Phase 3: Structured Reports and Alerts

Goal:

Generate routine health reports and urgent alerts.

Build:

- 12-hour report generator
- immediate critical loop
- severity classification
- alert cooldowns
- Telegram notifications
- all-okay reports
- report history view

Report sections:

- overall status
- critical issues
- warnings
- backups
- mail
- SSL
- disk/inodes
- services
- resource offenders
- stale collectors
- recommended manual review

Deliverable:

- twice-daily operational report
- critical alerts
- dashboard report viewer

---

Phase 4: Action Catalog and Executor

Goal:

Create safe action foundation.

Build:

- action catalog schema
- deterministic executor
- dry-run mode
- validation system
- cooldowns
- rate limits
- mutex locks
- pre-checks
- post-checks
- audit logs
- rejected-action logging

Initial actions:

- "CHECK_SSL_FOR_DOMAIN"
- "RUN_AUTOSSL_FOR_DOMAIN"
- "RESTART_EXIM"
- "RESTART_DOVECOT"
- "RESTART_LITESPEED"
- "RESTART_DNS_SERVICE"
- "CHECK_MAIL_HEALTH_FOR_DOMAIN"
- "CHECK_BACKUP_FOR_ACCOUNT"
- "REFRESH_BACKUP_STATUS"
- "CLEAR_LSCACHE_FOR_ACCOUNT"
- "GET_TOP_DISK_USERS"
- "GET_TOP_INODE_USERS"

Deliverable:

- safe executor
- action API
- dry-run action testing
- no generic command execution

---

Phase 5: Manual Safe Actions in Dashboard

Goal:

Expose selected actions as manual buttons.

Requirements:

- explicit confirmation
- target display
- risk label
- dry-run preview where useful
- action result display
- post-check result display
- full audit log
- role-based permissions

Allowed manual actions:

- restart LiteSpeed
- restart Exim
- restart Dovecot
- restart DNS
- run AutoSSL
- clear LSCache
- refresh backup status
- run diagnostics

Deliverable:

- dashboard safe-action buttons

---

Phase 6: Codex Review Layer

Goal:

Let Codex review structured reports safely.

Build:

- Codex input schema
- Codex output schema
- recommendation parser
- allowed action ID validation
- missing-action queue
- UI display of AI summaries
- policy engine integration

Codex may recommend.

Codex may not execute.

Deliverable:

- Codex-assisted report review
- safe recommendations only
- missing-action queue

---

Phase 7: Tier 1 Auto-Fix (Post-MVP)

Goal:

Allow narrow low-risk auto-fixes.

Requirements:

- deterministic rule must detect issue
- policy engine must approve
- action must be Tier 1
- pre-check must pass
- cooldown must pass
- lock must be available
- post-check must verify success
- notification must be sent
- audit log must be written

Eligible early examples:

- run AutoSSL for expiring cert
- restart Exim if stopped
- restart Dovecot if stopped
- restart LiteSpeed if stopped
- refresh JetBackup status
- restart DNS if stopped

Deliverable:

- supervised low-risk auto-fix pipeline

---

Phase 8: Telegram Approval Workflow (Post-MVP)

Goal:

Allow safe remote approval for approval-required actions.

Requirements:

- signed expiring buttons
- action summary
- target shown clearly
- risk tier shown clearly
- approval log
- rejection log
- post-action result notification
- no raw commands
- no arbitrary arguments

Deliverable:

- Telegram approval flow for predefined actions

---

Phase 9: Hardening and Operationalization (Post-MVP)

Goal:

Make it production-safe long term.

Add:

- emergency pause/read-only mode
- Cockpit self-monitoring
- deployment hardening
- Cockpit SQLite database backup: automated daily backup to a separate location (off the WHM server where possible, or at minimum to a separate partition/path); backup must include the full database file and the policy engine TOML file; retention of at least 7 daily snapshots; backup failure must trigger a Telegram alert; backup integrity must be verified by attempting to open the backup file after each run
- Cockpit policy file backup: version-controlled in git with remote; local git history is not sufficient
- documented runbooks
- action promotion workflow
- test suite
- disaster recovery notes
- monitoring of Cockpit itself
- process isolation improvements

Deliverable:

- stable internal production ops system

---

25. Testing Plan

Before automation:

- unit test validators
- test action catalog parser
- test argument validation
- test shell escaping
- test stale-data logic
- simulate collector failures
- simulate service down state where safe
- fake JetBackup failure data
- fake high mail queue data
- dry-run all actions
- manually execute actions before auto-fix eligibility
- verify all actions produce audit logs
- verify all post-checks work
- verify emergency pause blocks automation

---

26. MVP Success Criteria

The MVP is successful when the operator can:

1. Open one dashboard and know server health.
2. Identify urgent issues within 30 seconds.
3. Search account/domain and see operational state.
4. Confirm backup availability for an account.
5. Diagnose common mail, SSL, DNS, disk, and service issues.
6. Receive useful 12-hour reports.
7. Receive urgent Telegram alerts.
8. Run safe manual actions from the dashboard.
9. Escalate to WHM with one click.
10. See complete audit history.
11. Know when telemetry is stale.
12. Pause automation instantly.
13. Prevent Codex from executing anything outside approved actions.

MVP covers Phases 1 through 6.

Phases 7, 8, and 9 are post-MVP and must not be treated as MVP delivery targets.

---

27. Client Area Read-Only Telemetry API

The Cockpit exposes a read-only telemetry API for the custom Next.js client area built over WHMCS.

Full specification is in Phase 2.5 of the Implementation Plan.

Summary:

- Cockpit collects per-account stats, suspension status, and HTTP health data on defined schedules.
- Next.js queries WHMCS GetClientsProducts to resolve account ownership.
- Next.js queries Cockpit batch stats API server-side using a shared API key.
- WHMCS is the access control boundary. Cockpit API is authorization-agnostic.
- All responses include request_id, cached_at, collected_at, expires_at, and freshness fields.
- Online status becomes UNKNOWN after 5 minutes of staleness.
- Suspension status has a 60-second TTL.
- Next.js client area implements stale-while-revalidate with a "Last updated" indicator.
- Multi-server routing must be built now via serverid map even if only one server exists.
- **Client-safe schema only** — no internal operator data exposed (see §2 in addendum).

---

28. Final Philosophy

Cockpit is not an AI sysadmin.

Cockpit is a bounded operations assistant.

It combines:

- reliable telemetry
- human-first dashboard
- deterministic actions
- strict action catalog
- Codex-assisted reasoning
- auditability
- safe automation
- WHM escalation

The guiding rule:

«AI can choose from buttons. Only the operator can create buttons.»