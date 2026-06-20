The current state of the `harryneopotter/whm-agent-cockpit` repository contains several incomplete features, bugs and areas needing refinement. Below is a consolidated list of the main issues found during the code review.

### 1. Policy Engine still incomplete

The `PolicyEngine` class that governs auto‑run policies still contains unimplemented logic for crucial gates. Specifically, the `evaluate()` method has TODOs for:

* Checking **consecutive detections** – to prevent repeated auto‑actions when the same issue keeps reoccurring.
* Enforcing **cooldown periods** – to avoid running the same action too often.
* Applying **rate‑limit checks** based on the audit log.

Because these checks are missing, the policy engine cannot properly determine whether an auto‑action should be permitted, risking over‑aggressive remediation.

### 2. Executor lacks post‑execution verification & audit logging

The `Executor` (`src/cockpit/executor/runner.py`) executes defined actions but still contains a TODO for **post‑action checks and audit log writing**. Without these, the system cannot verify whether an action succeeded or log what was done, undermining traceability and reliability.

### 3. Environment variable typo in database migration

The migration script (`src/cockpit/db/migrate.py`) reads the database path from the variable `COCKPI_DB_PATH`. This appears to be a typo; it should be `COCKPIT_DB_PATH`. As a result, the migrations may ignore the configured DB path and use a default location, which could lead to data being stored in unexpected places.

### 4. Unused / extraneous code in collectors

Several collectors have leftover code:

* In `server_health.py`, `_disk_usage()` contains a loop over `shutil.disk_usage('/')` that performs no operations (it simply calls `pass`), suggesting a remnant from earlier debugging.
* Such unused loops should be removed to avoid confusion and ensure the code path is clear.

### 5. HTTP health collector incomplete

The `HTTPHealthCollector` (`collectors/http_health.py`) currently:

* Performs only edge checks using HEAD requests.
* Leaves the fields `origin_status`, `ssl_valid`, and `ssl_days_remaining` unpopulated or hard‑coded.
* Doesn’t use `curl --resolve` or SNI‑correct checks, and doesn’t implement concurrency/jitter control as outlined in the addendum【turn52file0†L70-L97】.

Because of these gaps, the collector may misclassify website status or miss SSL‑related problems.

### 6. JetBackup collector placeholders

The JetBackup collector’s methods `_failed_accounts()` and `_accounts_missing_backup()` return empty lists, meaning the collector does not yet report backup failures or accounts with missing backups. This leaves a critical gap in backup monitoring.

### 7. Incomplete SSL expiry collector

The SSL expiry collector only retrieves `days_remaining` and `issuer` but does not populate fields such as `valid_from`, `valid_to` or `auto_ssl_enabled`. It also doesn’t handle domains beyond primary domains. More comprehensive SSL metadata and coverage are needed.

### 8. Service name assumptions

The `service_status.py` collector checks status for services such as `litespeed.service` and `cpanel.service`. If the actual service names differ on target servers, these checks may fail. A more robust approach might allow service names to be configured via environment or policy.

### 9. Policy/addendum features not implemented

The repository includes an addendum (`cockpit-prd-v2-required-changes-addendum.md`) describing improvements such as origin health checks, client‑safe vs. operator-safe stats schemas, concurrency limits, jitter, and backup restore readiness. The current code does not appear to implement many of these changes, especially for the HTTP health collector and client telemetry API.

### Overall recommendations

* Implement the remaining policy gates (consecutive detection, cooldown, rate limits) and ensure the executor logs actions and performs post‑checks.
* Fix the environment variable typo (`COCKPI_DB_PATH`) to prevent misconfigured database paths.
* Remove unused loops and ensure collectors are doing meaningful work.
* Fully implement JetBackup status reporting and enhance SSL expiry collection.
* Update the HTTP health collector to perform origin checks, calculate SSL validity, and handle concurrency/jitter as specified in the addendum.
* Review service names to allow configuration flexibility.
* Integrate addendum features into the codebase to align with the design goals.

Addressing these issues will make the cockpit more reliable, secure, and aligned with its product requirements.
