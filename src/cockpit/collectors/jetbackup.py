"""JetBackup Collector — backup status, failed accounts, restore readiness."""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any

from cockpit.collectors.base import BaseCollector


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

    def _run_cli(self, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess | None:
        """Run jetbackup CLI with arguments."""
        cli = self._jetbackup_cli()
        if not cli:
            return None
        try:
            return subprocess.run(
                [cli, *args],
                capture_output=True, text=True, timeout=timeout,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

    def _check_destination(self) -> bool:
        """Check if backup destination is reachable via CLI status output."""
        result = self._run_cli(["--status"], timeout=15)
        if not result:
            return False
        # Look for destination status in output
        for line in result.stdout.split("\n"):
            if "destination" in line.lower() and ("ok" in line.lower() or "reachable" in line.lower()):
                return True
            if "destination" in line.lower() and ("fail" in line.lower() or "unreachable" in line.lower()):
                return False
        # If CLI returned successfully, assume reachable
        return result.returncode == 0

    def _last_run(self) -> str | None:
        """Get last backup run timestamp from JetBackup CLI output."""
        result = self._run_cli(["--status"])
        if not result:
            return None
        for line in result.stdout.split("\n"):
            # Common formats: "Last Run: 2026-06-17 02:00:00" or "last_run: 2026-06-17T02:00:00Z"
            match = re.search(r"(?:last\s+run|last_run)\s*:\s*(\S[\S\s]{0,40}?)(?:\n|$)", line, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _failed_accounts(self) -> list[str]:
        """Parse failed accounts from JetBackup CLI --list-failed or --status output."""
        result = self._run_cli(["--list-failed"])
        if result and result.stdout.strip():
            accounts = []
            for line in result.stdout.split("\n"):
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("-"):
                    # Lines are typically just usernames or "username - reason"
                    acct = line.split()[0] if line.split() else ""
                    if acct and acct not in accounts:
                        accounts.append(acct)
            return accounts

        # Fallback: try parsing --status for failed account mentions
        result = self._run_cli(["--status"])
        if result:
            accounts = []
            for line in result.stdout.split("\n"):
                if "failed" in line.lower():
                    # Try to extract account names from "user@domain failed" patterns
                    parts = line.split()
                    for part in parts:
                        if "@" in part or (part.islower() and len(part) < 20 and not part.startswith("-")):
                            acct = part.split("@")[0]
                            if acct and acct not in accounts:
                                accounts.append(acct)
            return accounts

        return []

    def _accounts_missing_backup(self) -> list[str]:
        """Compare JetBackup status against WHM account list for gaps.

        Parses backup list from JetBackup and returns accounts without recent backups.
        """
        result = self._run_cli(["--list-backups"])
        if not result:
            return []

        backed_up: set[str] = set()
        for line in result.stdout.split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                # Lines may be "username" or "username  2026-06-17"
                acct = line.split()[0] if line.split() else ""
                if acct:
                    backed_up.add(acct)

        # Compare against WHM account list from DB
        try:
            import sqlite3
            conn = sqlite3.connect(self._db_path)
            cursor = conn.execute("SELECT username FROM whm_accounts")
            all_accounts = {row[0] for row in cursor.fetchall()}
            conn.close()
        except Exception:
            return []

        missing = list(all_accounts - backed_up)
        missing.sort()
        return missing
