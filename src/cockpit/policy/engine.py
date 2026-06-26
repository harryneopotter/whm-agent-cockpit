"""Policy Engine — controls whether actions may auto-run or require approval.

Policy is stored as a TOML file at a defined path, version-controlled in git,
and NOT writable by any automated process or Codex.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from cockpit.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ActionPolicy:
    """Per-action policy settings."""

    auto_run: bool = False
    require_consecutive_detections: int = 1
    cooldown_seconds: int = 300
    max_per_24h: int = 10
    notify_before: bool = False
    notify_after: bool = True
    enabled: bool = True
    block_after_postcheck_failures: int = 1
    require_manual_ack_after_failure: bool = True


class PolicyEngine:
    """Reads and evaluates policy from TOML config.

    Decision order (all must pass for auto-run):
    1. enabled?
    2. auto_run?
    3. consecutive detections met?
    4. cooldown passed?
    5. max_per_24h not reached?
    6. circuit breaker (post-check failures)?
    7. pre-checks pass?

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
                        require_consecutive_detections=entry.get("require_consecutive_detections", 1),
                        cooldown_seconds=entry.get("cooldown_seconds", 300),
                        max_per_24h=entry.get("max_per_24h", 10),
                        notify_before=entry.get("notify_before", False),
                        notify_after=entry.get("notify_after", True),
                        enabled=entry.get("enabled", True),
                        block_after_postcheck_failures=entry.get("block_after_postcheck_failures", 1),
                        require_manual_ack_after_failure=entry.get("require_manual_ack_after_failure", True),
                    )
                logger.info("Policy loaded: %d actions from %s", len(self._policies), self._path)
            else:
                logger.warning("Policy file %s not found — all auto-run disabled", self._path)
        except Exception as exc:
            logger.error("Failed to load policy %s: %s — fallback to all-blocked", self._path, exc)

    def evaluate(
        self,
        action: Any,
        target: str | None = None,
        mode: Literal["manual", "auto"] = "manual",
        issue_id: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate whether an action is allowed.

        Args:
            action: ActionDef from the catalog
            target: target of the action (service name, domain, etc.)
            mode: "manual" (dashboard button click) or "auto" (Codex/policy trigger)
            issue_id: explicit issue ID that triggered this evaluation (avoids string guessing)

        Returns dict with:
          - allowed: bool
          - reason: str
          - checks: dict of individual gate results
        """
        from cockpit.executor.catalog import ActionDef
        assert isinstance(action, ActionDef), "action must be ActionDef"

        policy = self._policies.get(action.action_id)
        result: dict[str, Any] = {
            "action_id": action.action_id,
            "target": target,
            "mode": mode,
            "allowed": False,
            "reason": "",
            "checks": {},
        }

        # Gate 1: enabled?
        if policy and not policy.enabled:
            result["reason"] = f"Action {action.action_id} is disabled in policy"
            result["checks"]["enabled"] = False
            return result

        if mode == "auto":
            # Auto mode: auto_run must be true
            if not policy or not policy.auto_run:
                result["reason"] = "Auto-approval required (auto_run=false in policy) — queue for operator approval"
                result["checks"]["auto_run"] = False
                result["checks"]["enabled"] = True
                return result

            # Auto-run: check all gates
            return self._check_auto_run_gates(action, policy, target, issue_id)

        # Manual mode: allow but flag approval requirement
        result["allowed"] = True
        if policy and not policy.auto_run:
            result["reason"] = "Approval required (auto_run=false)"
            result["approval_required"] = True
        else:
            result["reason"] = "Manual action — proceeding"
        result["checks"]["enabled"] = True
        return result

    def _check_auto_run_gates(
        self,
        action: Any,
        policy: ActionPolicy,
        target: str | None,
        issue_id: str | None,
    ) -> dict[str, Any]:
        """Run all auto-run gates against the DB."""
        result: dict[str, Any] = {
            "action_id": action.action_id,
            "target": target,
            "mode": "auto",
            "allowed": False,
            "reason": "",
            "checks": {},
        }
        checks: dict[str, bool] = {}
        checks["enabled"] = True
        checks["auto_run"] = True

        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(settings.db_path)
            conn.row_factory = sqlite3.Row

            # Gate 3: consecutive detections
            checks["consecutive_detections_met"] = self._check_consecutive_detections(
                conn, action, issue_id, policy.require_consecutive_detections
            )

            # Gate 4: cooldown
            checks["cooldown_passed"] = self._check_cooldown(
                conn, action.action_id, policy.cooldown_seconds
            )

            # Gate 5: rate limit
            checks["rate_limit_ok"] = self._check_rate_limit(
                conn, action.action_id, policy.max_per_24h
            )

            # Gate 6: circuit breaker
            checks["circuit_breaker_ok"] = self._check_circuit_breaker(
                conn, action.action_id, action.post_check_service,
                policy.block_after_postcheck_failures,
            )

        except Exception:
            logger.exception("Policy gate check failed")
            for k in ("consecutive_detections_met", "cooldown_passed", "rate_limit_ok", "circuit_breaker_ok"):
                checks.setdefault(k, False)
        finally:
            if conn:
                conn.close()

        all_pass = all(checks.values())
        result["allowed"] = all_pass
        result["checks"] = checks
        if not all_pass:
            failed = [k for k, v in checks.items() if not v]
            result["reason"] = f"Policy checks failed: {', '.join(failed)}"
        else:
            result["reason"] = "All policy checks passed"

        return result

    @staticmethod
    def _check_consecutive_detections(
        conn: sqlite3.Connection,
        action: Any,
        issue_id: str | None,
        required: int,
    ) -> bool:
        """Check consecutive detections using explicit issue IDs from the action def.

        Uses action.related_issue_ids (explicit mapping) first.
        Falls back to issue_id parameter if provided.
        Avoids string-guessing issue IDs.
        """
        candidate_ids: list[str] = []
        if action.related_issue_ids:
            candidate_ids = list(action.related_issue_ids)
        elif issue_id:
            candidate_ids = [issue_id]

        if not candidate_ids:
            return True  # no issue tracking needed for this action

        for iid in candidate_ids:
            row = conn.execute(
                "SELECT consecutive_detections FROM issues WHERE issue_id = ? "
                "AND state NOT IN ('RESOLVED', 'SUPPRESSED')",
                (iid,),
            ).fetchone()
            if row and row["consecutive_detections"] >= required:
                return True

        return False

    @staticmethod
    def _check_cooldown(
        conn: sqlite3.Connection,
        action_id: str,
        cooldown_seconds: int,
    ) -> bool:
        """Check cooldown from audit_log. Handles both naive and aware timestamps."""
        row = conn.execute(
            "SELECT created_at FROM audit_log WHERE "
            "(event_type = 'action_executed' OR event_type = 'action_failed') "
            "AND json_extract(data, '$.action_id') = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (action_id,),
        ).fetchone()
        if not row:
            return True  # never run

        try:
            last = datetime.fromisoformat(row["created_at"])
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            elapsed = (now - last).total_seconds()
            return elapsed >= cooldown_seconds
        except (ValueError, TypeError):
            logger.warning("Could not parse cooldown timestamp: %s", row["created_at"])
            return False

    @staticmethod
    def _check_rate_limit(
        conn: sqlite3.Connection,
        action_id: str,
        max_per_24h: int,
    ) -> bool:
        """Check executions in last 24h from audit_log."""
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM audit_log WHERE "
            "(event_type = 'action_executed' OR event_type = 'action_failed') "
            "AND json_extract(data, '$.action_id') = ? AND created_at >= ?",
            (action_id, since),
        ).fetchone()
        count = row["cnt"] if row else 0
        return count < max_per_24h

    @staticmethod
    def _check_circuit_breaker(
        conn: sqlite3.Connection,
        action_id: str,
        post_check_service: str | None,
        max_failures: int,
    ) -> bool:
        """Check if the circuit breaker has tripped.

        Counts action_failed events for this action in the last 24h.
        Also checks for specific service-level post-check failures.
        """
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

        # Count all failures for this action_id
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM audit_log WHERE event_type = 'action_failed' "
            "AND json_extract(data, '$.action_id') = ? AND created_at >= ?",
            (action_id, since),
        ).fetchone()
        failures = row["cnt"] if row else 0

        if failures >= max_failures:
            logger.warning(
                "Circuit breaker tripped for %s: %d failures in 24h (limit %d)",
                action_id, failures, max_failures,
            )
            return False

        # Also check service-level failures if applicable
        if post_check_service:
            # Look for post_check_failed status on this service
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM audit_log WHERE event_type = 'action_failed' "
                "AND json_extract(data, '$.action_id') = ? "
                "AND json_extract(data, '$.status') = 'post_check_failed' "
                "AND created_at >= ?",
                (action_id, since),
            ).fetchone()
            service_failures = row["cnt"] if row else 0

            # For service failures, be more conservative
            if service_failures >= max_failures:
                logger.warning(
                    "Service circuit breaker tripped for %s: %d post-check failures in 24h",
                    action_id, service_failures,
                )
                return False

        return True
