"""Mail Queue Collector — Exim queue size, frozen count, and error rate."""

from __future__ import annotations

import subprocess
import re
from typing import Any

from cockpit.collectors.base import BaseCollector, CollectorError


class MailQueueCollector(BaseCollector):
    """Check Exim mail queue via CLI and log errors via journalctl."""

    name = "mail_queue"

    async def poll(self) -> dict[str, list[dict[str, Any]]]:
        now = self.now_iso()
        queue_size = self._queue_size()
        frozen_count = self._frozen_count()
        errors_last_hour = self._exim_errors_last_hour()

        return {
            "mail_queue": [{
                "collected_at": now,
                "queue_size": queue_size,
                "frozen_count": frozen_count,
                "exim_errors_last_hour": errors_last_hour,
                "ttl_seconds": 120,
            }],
        }

    @staticmethod
    def _queue_size() -> int | None:
        """Run exim -bpc for total queue count."""
        try:
            result = subprocess.run(
                ["exim", "-bpc"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return int(result.stdout.strip())
            return None
        except (FileNotFoundError, ValueError, subprocess.TimeoutExpired):
            return None

    @staticmethod
    def _frozen_count() -> int | None:
        """Count frozen messages via exim -bp | grep frozen."""
        try:
            result = subprocess.run(
                ["exim", "-bp"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                return None
            count = 0
            for line in result.stdout.split("\n"):
                if "frozen" in line.lower():
                    count += 1
            return count
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

    @staticmethod
    def _exim_errors_last_hour() -> int | None:
        """Count Exim errors in the last hour from journalctl."""
        try:
            result = subprocess.run(
                ["journalctl", "-u", "exim", "--since", "1 hour ago", "--no-pager"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return None
            # Count lines with "error" or "failed" or "rejected"
            count = 0
            for line in result.stdout.split("\n"):
                if re.search(r"\berror\b|\bfailed\b|\brejected\b", line, re.IGNORECASE):
                    count += 1
            return count
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
