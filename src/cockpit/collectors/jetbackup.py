"""JetBackup Collector — backup status, failed accounts, restore readiness."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from cockpit.collectors.base import BaseCollector, CollectorError


class JetBackupCollector(BaseCollector):
    """Check JetBackup status via CLI (jetbackup or jetbackup5)."""

    name = "jetbackup"

    async def poll(self) -> dict[str, list[dict[str, Any]]]:
        now = self.now_iso()
        status = self._check_destination()
        last_run = self._last_run()
        failed = self._failed_accounts()
        missing = self._accounts_missing_backup()

        return {
            "jetbackup_status": [{
                "collected_at": now,
                "destination_reachable": 1 if status else 0,
                "last_run_at": last_run,
                "failed_accounts": json.dumps(failed),
                "accounts_missing_recent_backup": json.dumps(missing),
                "restore_point_counts": "{}",
                "ttl_seconds": 600,
            }],
        }

    @staticmethod
    def _jetbackup_cli() -> str | None:
        """Find the jetbackup CLI binary."""
        for candidate in ["jetbackup5", "jetbackup", "jetbackup3"]:
            try:
                result = subprocess.run(
                    ["which", candidate],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return candidate
            except FileNotFoundError:
                continue
        return None

    def _check_destination(self) -> bool:
        """Check if backup destination is reachable."""
        cli = self._jetbackup_cli()
        if not cli:
            return False
        try:
            result = subprocess.run(
                [cli, "--check-destination"],
                capture_output=True, text=True, timeout=30,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _last_run(self) -> str | None:
        """Get last backup run timestamp."""
        cli = self._jetbackup_cli()
        if not cli:
            return None
        try:
            result = subprocess.run(
                [cli, "--status"],
                capture_output=True, text=True, timeout=30,
            )
            # Parse output for "Last Run" or equivalent
            for line in result.stdout.split("\n"):
                if "last run" in line.lower():
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        return parts[1].strip()
            return None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

    @staticmethod
    def _failed_accounts() -> list[str]:
        """Placeholder — JetBackup CLI output parsing is version-specific."""
        return []

    @staticmethod
    def _accounts_missing_backup() -> list[str]:
        """Placeholder — would compare JetBackup status against WHM account list."""
        return []
