"""WHM Account List Collector — fetches all cPanel accounts via WHM API."""

from __future__ import annotations

from typing import Any

from cockpit.collectors.base import BaseCollector
from cockpit.whm_client import WHMClient


class WHMAccountsCollector(BaseCollector):
    """Fetch all cPanel accounts via WHM listaccts API."""

    name = "whm_accounts"

    async def poll(self) -> dict[str, list[dict[str, Any]]]:
        now = self.now_iso()
        client = WHMClient()
        try:
            accounts = client.list_accounts()
            rows: list[dict[str, Any]] = []
            for acct in accounts:
                rows.append({
                    "username": acct.username,
                    "collected_at": now,
                    "domain": acct.domain,
                    "plan_name": acct.plan_name,
                    "disk_used_mb": acct.disk_used_mb,
                    "disk_limit_mb": acct.disk_limit_mb,
                    "bandwidth_used_mb": acct.bandwidth_used_mb,
                    "bandwidth_limit_mb": acct.bandwidth_limit_mb,
                    "email_count": acct.email_count,
                    "db_count": acct.db_count,
                    "subdomain_count": acct.subdomain_count,
                    "addon_domain_count": acct.addon_domain_count,
                    "parked_domain_count": acct.parked_domain_count,
                    "php_version": acct.php_version,
                    "suspended": 1 if acct.suspended else 0,
                    "ttl_seconds": 600,
                })
            # Also update suspension_status table
            suspension_rows = []
            for acct in accounts:
                suspension_rows.append({
                    "username": acct.username,
                    "collected_at": now,
                    "suspended": 1 if acct.suspended else 0,
                    "ttl_seconds": 60,
                })

            return {
                "whm_accounts": rows,
                "suspension_status": suspension_rows,
            }
        finally:
            client.close()
