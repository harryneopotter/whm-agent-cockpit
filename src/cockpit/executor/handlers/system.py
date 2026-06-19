"""System-level action handlers — deterministic, no shell injection surface."""

from __future__ import annotations

import subprocess
from typing import Any


def _systemctl(action: str, service: str) -> dict[str, Any]:
    """Run systemctl for a service. Returns structured result."""
    try:
        result = subprocess.run(
            ["systemctl", action, service],
            capture_output=True, text=True, timeout=30,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return {"success": False, "error": str(e)}


def restart_exim(target: str | None = None, **kwargs: Any) -> dict[str, Any]:
    """Restart Exim mail service (Tier 1)."""
    return _systemctl("restart", "exim")


def restart_dovecot(target: str | None = None, **kwargs: Any) -> dict[str, Any]:
    """Restart Dovecot (Tier 1)."""
    return _systemctl("restart", "dovecot")


def restart_litespeed(target: str | None = None, **kwargs: Any) -> dict[str, Any]:
    """Restart LiteSpeed (Tier 1)."""
    return _systemctl("restart", "lsws")


def check_service_status(service: str | None = None, **kwargs: Any) -> dict[str, Any]:
    """Check if a service is running (Tier 0 read-only)."""
    if not service:
        return {"success": False, "error": "service name required"}
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True, text=True, timeout=10,
        )
        return {
            "success": True,
            "service": service,
            "status": result.stdout.strip(),
        }
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return {"success": False, "error": str(e)}
