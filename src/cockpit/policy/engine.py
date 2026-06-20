"""Policy Engine — controls whether actions may auto-run or require approval.

Policy is stored as a TOML file at a defined path, version-controlled in git,
and NOT writable by any automated process or Codex.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cockpit.config import settings

logger = logging.getLogger(__name__)

POLICY_FALLBACK = """# Cockpit Policy Engine — fallback (loaded when policy file is missing)
# Default: all auto-run disabled, monitoring continues.

# Default catch-all: no actions auto-run
[actions]
"""


@dataclass
class ActionPolicy:
    """Per-action policy settings."""

    auto_run: bool = False
    require_consecutive_detections: int = 1
    cooldown_seconds: int = 300
    max_per_24h: int = 10
    notify_before: bool = False
    notify_after: bool = True  # addendum §10: default true
    enabled: bool = True
    block_after_postcheck_failures: int = 1  # addendum §9
    require_manual_ack_after_failure: bool = True  # addendum §9


class PolicyEngine:
    """Reads and evaluates policy from TOML config.

    Decision order (all must pass for auto-run):
    1. enabled?
    2. auto_run?
    3. consecutive detections met?
    4. cooldown passed?
    5. max_per_24h not reached?
    6. pre-checks pass?

    Fallback: if policy file cannot be loaded, all auto_run = false.
    """

    def __init__(self, policy_path: str | None = None) -> None:
        self._path = Path(policy_path or settings.policy_path)
        self._policies: dict[str, ActionPolicy] = {}
        self._load()

    def _load(self) -> None:
        """Load policy from TOML file. Falls back to safe defaults."""
        try:
            import tomli
            if self._path.exists():
                with self._path.open("rb") as f:
                    data = tomli.load(f)
                for action_id, entry in data.get("actions", {}).items():
                    self._policies[action_id] = ActionPolicy(
                        auto_run=entry.get("auto_run", False),
                        require_consecutive_detections=entry.get(
                            "require_consecutive_detections", 1
                        ),
                        cooldown_seconds=entry.get("cooldown_seconds", 300),
                        max_per_24h=entry.get("max_per_24h", 10),
                        notify_before=entry.get("notify_before", False),
                        notify_after=entry.get("notify_after", True),
                        enabled=entry.get("enabled", True),
                        block_after_postcheck_failures=entry.get(
                            "block_after_postcheck_failures", 1
                        ),
                        require_manual_ack_after_failure=entry.get(
                            "require_manual_ack_after_failure", True
                        ),
                    )
                logger.info(
                    "Policy loaded: %d actions from %s",
                    len(self._policies), self._path,
                )
            else:
                logger.warning("Policy file %s not found — all auto-run disabled", self._path)
        except Exception as exc:
            logger.error("Failed to load policy %s: %s — fallback to all-blocked", self._path, exc)

    def evaluate(self, action: Any, target: str | None = None) -> dict[str, Any]:
        """Evaluate whether an action is allowed to auto-run.

        Queries the DB for consecutive detections (issues table), cooldown,
        and rate limits (audit_log table).

        Returns dict with:
          - allowed: bool
          - reason: str
          - checks: dict of individual gate results
        """
        from cockpit.executor.catalog import ActionDef
        import sqlite3, json
        assert isinstance(action, ActionDef), "action must be ActionDef"

        policy = self._policies.get(action.action_id)
        result: dict[str, Any] = {
            "action_id": action.action_id,
            "target": target,
            "allowed": False,
            "reason": "",
            "checks": {},
        }

        # Gate 1: enabled?
        if policy and not policy.enabled:
            result["reason"] = f"Action {action.action_id} is disabled in policy"
            result["checks"]["enabled"] = False
            return result
        if not policy or not policy.auto_run:
            result["allowed"] = True  # manual is still allowed
            result["reason"] = "Approval required (auto_run=false)"
            result["checks"]["auto_run"] = False
            result["checks"]["enabled"] = True
            return result

        checks: dict[str, bool] = {}
        checks["enabled"] = True
        checks["auto_run"] = True

        # Gate 3: consecutive detections — read from issues table
        try:
            conn = sqlite3.connect(settings.db_path)
            conn.row_factory = sqlite3.Row
            issue_id = f"{action.action_id.lower()}_{target}" if target else None
            if issue_id:
                row = conn.execute(
                    "SELECT consecutive_detections FROM issues WHERE issue_id = ? "
                    "AND state NOT IN ('RESOLVED', 'SUPPRESSED')",
                    (issue_id,),
                ).fetchone()
                detections = row["consecutive_detections"] if row else 0
                checks["consecutive_detections_met"] = (
                    detections >= policy.require_consecutive_detections
                )
            else:
                checks["consecutive_detections_met"] = True
        except Exception:
            checks["consecutive_detections_met"] = False

        # Gate 4: cooldown — last execution time from audit_log
        try:
            row = conn.execute(
                "SELECT created_at FROM audit_log WHERE event_type = 'action_executed' "
                "AND json_extract(data, '$.action_id') = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (action.action_id,),
            ).fetchone()
            if row:
                from datetime import datetime, timezone
                last = datetime.fromisoformat(row["created_at"])
                now = datetime.now(timezone.utc)
                elapsed = (now - last).total_seconds()
                checks["cooldown_passed"] = elapsed >= policy.cooldown_seconds
            else:
                checks["cooldown_passed"] = True  # never run
        except Exception:
            checks["cooldown_passed"] = False

        # Gate 5: rate limit — count in last 24h
        try:
            from datetime import datetime, timedelta, timezone
            since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM audit_log WHERE event_type = 'action_executed' "
                "AND json_extract(data, '$.action_id') = ? AND created_at >= ?",
                (action.action_id, since),
            ).fetchone()
            count_24h = row["cnt"] if row else 0
            checks["rate_limit_ok"] = count_24h < policy.max_per_24h
            conn.close()
        except Exception:
            checks["rate_limit_ok"] = False

        all_pass = all(checks.values())
        result["allowed"] = all_pass
        result["checks"] = checks
        if not all_pass:
            failed = [k for k, v in checks.items() if not v]
            result["reason"] = f"Policy checks failed: {', '.join(failed)}"
        else:
            result["reason"] = "All policy checks passed"

        return result
