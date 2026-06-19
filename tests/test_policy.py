"""Tests for the policy engine."""

import tempfile
from pathlib import Path

import pytest

from cockpit.executor.catalog import ActionDef, RiskTier, register
from cockpit.policy.engine import PolicyEngine, ActionPolicy


@pytest.fixture
def read_only_action() -> ActionDef:
    action = ActionDef(
        action_id="TEST_READ_ONLY",
        description="Test read-only action",
        risk_tier=RiskTier.READ_ONLY,
        target_type=None,
    )
    register(action)
    return action


@pytest.fixture
def policy_file() -> str:
    content = """[actions.TEST_READ_ONLY]
auto_run = true
enabled = true
cooldown_seconds = 10
max_per_24h = 100
notify_after = true
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(content)
        return f.name


class TestPolicyEngine:
    def test_load_from_file(self, policy_file: str) -> None:
        engine = PolicyEngine(policy_file)
        assert "TEST_READ_ONLY" in engine._policies
        assert engine._policies["TEST_READ_ONLY"].auto_run

    def test_missing_file_defaults_to_blocked(self) -> None:
        engine = PolicyEngine("/nonexistent/policy.toml")
        assert len(engine._policies) == 0

    def test_auto_run_allowed(self, read_only_action: ActionDef, policy_file: str) -> None:
        engine = PolicyEngine(policy_file)
        result = engine.evaluate(read_only_action)
        assert result["allowed"]

    def test_disabled_action(self, read_only_action: ActionDef) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("""[actions.TEST_READ_ONLY]
auto_run = false
enabled = false
""")
            path = f.name
        engine = PolicyEngine(path)
        result = engine.evaluate(read_only_action)
        assert not result["allowed"]
        assert "disabled" in result["reason"]

    def test_action_not_in_policy_defaults_require_approval(
        self, read_only_action: ActionDef
    ) -> None:
        engine = PolicyEngine.__new__(PolicyEngine)
        engine._policies = {}  # empty policy
        result = engine.evaluate(read_only_action)
        # Not in policy → allow manual, not auto-run
        assert result["allowed"]
        assert "Approval required" in result["reason"]
