"""Tests for the policy engine."""

import os
import tempfile
import sqlite3

import pytest

from cockpit.executor.catalog import ActionDef, RiskTier, register


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


@pytest.fixture
def temp_db() -> str:
    """Create a temp SQLite DB for policy engine tests."""
    db_path = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    # Create the tables policy engine queries
    conn.execute(
        "CREATE TABLE IF NOT EXISTS issues ("
        "  issue_id TEXT PRIMARY KEY, detected_at TEXT, severity TEXT,"
        "  state TEXT, description TEXT, consecutive_detections INTEGER DEFAULT 1,"
        "  target_type TEXT, target_id TEXT, ttl_seconds INTEGER"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS audit_log ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT DEFAULT (datetime('now')),"
        "  event_type TEXT, source TEXT, data TEXT"
        ")"
    )
    conn.commit()
    conn.close()
    yield db_path
    os.unlink(db_path)


class TestPolicyEngine:
    def test_load_from_file(self, policy_file: str) -> None:
        from cockpit.policy.engine import PolicyEngine
        engine = PolicyEngine(policy_file)
        assert "TEST_READ_ONLY" in engine._policies
        assert engine._policies["TEST_READ_ONLY"].auto_run

    def test_missing_file_defaults_to_blocked(self) -> None:
        from cockpit.policy.engine import PolicyEngine
        engine = PolicyEngine("/nonexistent/policy.toml")
        assert len(engine._policies) == 0

    def test_auto_run_allowed(
        self, read_only_action: ActionDef, policy_file: str, temp_db: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("COCKPIT_DB_PATH", temp_db)
        from cockpit.policy.engine import PolicyEngine
        # Reimport settings so it picks up the monkeypatched env
        import cockpit.config
        cockpit.config.settings.db_path = temp_db

        engine = PolicyEngine(policy_file)
        result = engine.evaluate(read_only_action)
        assert result["allowed"]

    def test_disabled_action(self, read_only_action: ActionDef, temp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COCKPIT_DB_PATH", temp_db)
        import cockpit.config
        cockpit.config.settings.db_path = temp_db

        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("""[actions.TEST_READ_ONLY]
auto_run = false
enabled = false
""")
            path = f.name
        from cockpit.policy.engine import PolicyEngine
        engine = PolicyEngine(path)
        result = engine.evaluate(read_only_action)
        assert not result["allowed"]
        assert "disabled" in result["reason"]

    def test_action_not_in_policy_defaults_require_approval(
        self, read_only_action: ActionDef, temp_db: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("COCKPIT_DB_PATH", temp_db)
        import cockpit.config
        cockpit.config.settings.db_path = temp_db

        from cockpit.policy.engine import PolicyEngine
        engine = PolicyEngine.__new__(PolicyEngine)
        engine._policies = {}  # empty policy
        result = engine.evaluate(read_only_action)
        assert result["allowed"]
        assert "Approval required" in result["reason"]

    def test_cooldown_enforced(
        self, read_only_action: ActionDef, policy_file: str, temp_db: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If a cooldown is active, auto-run should be blocked."""
        monkeypatch.setenv("COCKPIT_DB_PATH", temp_db)
        import cockpit.config
        cockpit.config.settings.db_path = temp_db

        # Insert a recent audit log entry
        conn = sqlite3.connect(temp_db)
        conn.execute(
            "INSERT INTO audit_log (created_at, event_type, source, data) "
            "VALUES (datetime('now'), 'action_executed', 'executor', '{\"action_id\": \"TEST_READ_ONLY\"}')"
        )
        conn.commit()
        conn.close()

        from cockpit.policy.engine import PolicyEngine
        engine = PolicyEngine(policy_file)
        result = engine.evaluate(read_only_action)
        # cooldown is 10s, and we just ran it — should fail
        assert not result["allowed"]
        assert "cooldown" in result["reason"] or "rate_limit" in result["reason"]
