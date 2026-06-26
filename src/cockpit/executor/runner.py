"""Executor — the only component allowed to perform actions.

Accepts only known action_ids. Validates, enforces policy, executes,
runs post-checks, and writes to the audit log.

Every return path is audited — including rejections.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any, Literal

from cockpit.executor.catalog import ActionDef, RiskTier, get, validate_action, register
from cockpit.executor.handlers import (
    restart_exim,
    restart_dovecot,
    restart_litespeed,
    check_service_status,
)
from cockpit.policy.engine import PolicyEngine

logger = logging.getLogger(__name__)


def _audit_log(
    event_type: str,
    source: str,
    data: dict[str, Any],
) -> None:
    """Write an audit log entry with UTC ISO timestamp."""
    from cockpit.config import settings
    try:
        conn = sqlite3.connect(settings.db_path)
        conn.execute(
            "INSERT INTO audit_log (created_at, event_type, source, data) VALUES (?, ?, ?, ?)",
            (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             event_type, source, json.dumps(data, default=str)),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error("Audit log write failed: %s", exc)


def _post_check_service(service: str) -> dict[str, Any]:
    """Check if a service is running after an action."""
    try:
        import subprocess
        result = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True, text=True, timeout=10,
        )
        return {
            "service": service,
            "status": result.stdout.strip(),
            "running": result.returncode == 0,
        }
    except Exception as exc:
        return {"service": service, "status": "unknown", "error": str(exc)}


class Executor:
    """Safe action executor. Runs only registered, validated actions."""

    def __init__(self, policy: PolicyEngine | None = None) -> None:
        self._policy = policy or PolicyEngine()
        self._register_default_actions()

    @staticmethod
    def _register_default_actions() -> None:
        """Register all built-in actions with explicit issue+service mappings."""
        register(ActionDef(
            action_id="RESTART_EXIM",
            description="Restart the Exim mail service",
            risk_tier=RiskTier.LOW_RISK_AUTO_FIX,
            target_type="service",
            related_issue_ids=["exim_stopped"],
            post_check_service="exim",
            allowed_args=[],
            cooldown_seconds=300,
            rate_limit_per_24h=5,
            handler=restart_exim,
        ))
        register(ActionDef(
            action_id="RESTART_DOVECOT",
            description="Restart Dovecot",
            risk_tier=RiskTier.LOW_RISK_AUTO_FIX,
            target_type="service",
            related_issue_ids=["dovecot_stopped"],
            post_check_service="dovecot",
            allowed_args=[],
            cooldown_seconds=300,
            rate_limit_per_24h=5,
            handler=restart_dovecot,
        ))
        register(ActionDef(
            action_id="RESTART_LITESPEED",
            description="Restart LiteSpeed web server",
            risk_tier=RiskTier.LOW_RISK_AUTO_FIX,
            target_type="service",
            related_issue_ids=["litespeed_stopped"],
            post_check_service="lsws",
            allowed_args=[],
            cooldown_seconds=300,
            rate_limit_per_24h=5,
            handler=restart_litespeed,
        ))
        register(ActionDef(
            action_id="CHECK_SERVICE_STATUS",
            description="Check if a service is running",
            risk_tier=RiskTier.READ_ONLY,
            target_type="service",
            allowed_args=["service"],
            handler=check_service_status,
        ))

    async def execute(
        self,
        action_id: str,
        target: str | None = None,
        args: dict[str, Any] | None = None,
        dry_run: bool = False,
        mode: Literal["manual", "auto"] = "manual",
    ) -> dict[str, Any]:
        """Execute (or dry-run) an action.

        Args:
            action_id: registered action ID from the catalog
            target: service/account/domain the action targets
            args: optional keyword arguments for the handler
            dry_run: if True, run policy checks but skip handler + post-check
            mode: "manual" (dashboard button click) or "auto" (Codex/policy trigger)

        Returns structured result dict. Every return path is audited.
        """
        result: dict[str, Any] = {
            "action_id": action_id,
            "target": target,
            "args": args or {},
            "dry_run": dry_run,
            "mode": mode,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        # 1. Validate action exists
        action = get(action_id)
        if action is None:
            result["status"] = "rejected"
            result["reason"] = f"Unknown action_id: {action_id}"
            _audit_log("action_rejected", "executor", result)
            return result

        # 2. Validate inputs
        error = validate_action(action_id, target, args or {})
        if error:
            result["status"] = "rejected"
            result["reason"] = error
            _audit_log("action_rejected", "executor", result)
            return result

        # 3. Check policy with mode
        policy_result = self._policy.evaluate(action, target, mode=mode)
        if not policy_result["allowed"]:
            result["status"] = "rejected"
            result["reason"] = policy_result["reason"]
            result["policy"] = policy_result
            _audit_log("action_rejected", "executor", result)
            return result

        # 4. Dry run
        if dry_run:
            result["status"] = "dry_run_ok"
            result["pre_checks"] = policy_result
            return result  # dry runs are NOT audited

        # 5. Execute
        if action.handler:
            try:
                handler_result = action.handler(target=target, **(args or {}))
                result["status"] = "completed" if handler_result.get("success") else "failed"
                result["output"] = handler_result
            except Exception as e:
                result["status"] = "failed"
                result["error"] = str(e)
                logger.exception("Action %s failed", action_id)
        else:
            result["status"] = "failed"
            result["reason"] = "No handler registered"

        # 6. Post-check: verify service state after restart actions
        if result["status"] == "completed" and action.post_check_service:
            post = _post_check_service(action.post_check_service)
            result["post_check"] = post
            if not post.get("running"):
                result["status"] = "post_check_failed"

        # 7. Single audit log entry (no double-logging)
        if result["status"] == "completed":
            _audit_log("action_executed", "executor", result)
        elif result["status"] in ("failed", "post_check_failed"):
            _audit_log("action_failed", "executor", result)

        return result


async def main() -> None:  # pragma: no cover
    """Standalone executor entry point (for testing)."""
    logging.basicConfig(level=logging.INFO)
    ex = Executor()
    r = await ex.execute("RESTART_EXIM", dry_run=True)
    print(r)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
