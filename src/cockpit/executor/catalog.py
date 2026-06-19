"""Action Catalog — the central contract for all allowed actions.

Every action is defined here with its risk tier, validation rules, and handler.
No generic actions (RUN_COMMAND, EXEC_SHELL, etc.) are permitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable


class RiskTier(IntEnum):
    READ_ONLY = 0
    LOW_RISK_AUTO_FIX = 1
    APPROVAL_REQUIRED = 2
    MANUAL_ONLY = 3


@dataclass
class ActionDef:
    """Definition of one action in the catalog."""

    action_id: str
    description: str
    risk_tier: RiskTier
    target_type: str | None  # "domain", "account", "service", or None
    allowed_args: list[str] = field(default_factory=list)
    approval_required: bool = False
    cooldown_seconds: int = 0
    rate_limit_per_24h: int = 0
    timeout_seconds: int = 30
    mutex_key: str | None = None
    enabled: bool = True
    # Handler is registered at startup; stored here for reference
    handler: Callable[..., Any] | None = None


# ── In-memory catalog ───────────────────────────────────────────────────

_catalog: dict[str, ActionDef] = {}


def register(action: ActionDef) -> None:
    """Register an action in the catalog."""
    _catalog[action.action_id] = action


def get(action_id: str) -> ActionDef | None:
    """Look up an action by ID."""
    return _catalog.get(action_id)


def list_actions() -> list[ActionDef]:
    """Return all registered actions."""
    return list(_catalog.values())


def validate_action(action_id: str, target: str | None, args: dict[str, Any]) -> str | None:
    """Validate an action invocation. Returns error message or None if valid."""
    action = _catalog.get(action_id)
    if action is None:
        return f"Unknown action_id: {action_id}"
    if not action.enabled:
        return f"Action {action_id} is disabled"
    if action.target_type and not target:
        return f"Action {action_id} requires a target"
    for key in args:
        if key not in action.allowed_args:
            return f"Unknown argument '{key}' for action {action_id}"
    return None
