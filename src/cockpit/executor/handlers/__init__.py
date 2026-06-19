"""Action handler implementations.

Each handler is a Python callable that performs one deterministic action.
Handlers must NOT accept arbitrary shell commands or scripts.
"""

from cockpit.executor.handlers.system import (
    restart_exim,
    restart_dovecot,
    restart_litespeed,
    check_service_status,
)

__all__ = [
    "restart_exim",
    "restart_dovecot",
    "restart_litespeed",
    "check_service_status",
]
