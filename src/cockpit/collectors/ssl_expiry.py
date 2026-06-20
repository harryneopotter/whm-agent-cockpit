"""SSL Expiry Collector — checks certificate expiry for all domains.

Uses WHM API list_ssl_certs where available, falls back to openssl CLI.
"""

from __future__ import annotations

import subprocess
import ssl
import socket
from datetime import datetime, timezone
from typing import Any

from cockpit.collectors.base import BaseCollector, CollectorError


class SSLExpiryCollector(BaseCollector):
    """Fetch SSL certificate expiry for all domains in the account list."""

    name = "ssl_expiry"

    async def poll(self) -> dict[str, list[dict[str, Any]]]:
        now = self.now_iso()
        domains = self._get_domains()
        rows: list[dict[str, Any]] = []

        for domain in domains:
            days_remaining, issuer, valid_from, valid_to = self._check_domain_ssl(domain)
            rows.append({
                "collected_at": now,
                "domain": domain,
                "issuer": issuer,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "days_remaining": days_remaining,
                "auto_ssl_enabled": None,
                "ttl_seconds": 3600,
            })

        return {"ssl_certs": rows}

    def _get_domains(self) -> list[str]:
        """Get unique domains from whm_accounts and domain_mapping."""
        import sqlite3
        conn = sqlite3.connect(self._db_path)
        try:
            rows = conn.execute(
                "SELECT DISTINCT domain FROM whm_accounts WHERE domain != ''"
            ).fetchall()
            domains = {r[0] for r in rows}
            # Also include addon, parked, and subdomains from domain_mapping
            try:
                extra = conn.execute(
                    "SELECT DISTINCT domain FROM domain_mapping WHERE domain != ''"
                ).fetchall()
                domains.update(r[0] for r in extra)
            except Exception:
                pass  # domain_mapping table may not exist yet
            return sorted(domains)
        finally:
            conn.close()

    @staticmethod
    def _check_domain_ssl(domain: str) -> tuple[int | None, str | None, str | None, str | None]:
        """Connect to domain:443 and check cert expiry.

        Returns (days_remaining, issuer, valid_from, valid_to).
        """
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = True
            ctx.verify_mode = ssl.CERT_REQUIRED
            with socket.create_connection((domain, 443), timeout=10) as sock:
                with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                    cert = ssock.getpeercert()
                    if not cert:
                        return (None, None, None, None)

                    not_after = cert.get("notAfter", "")
                    not_before = cert.get("notBefore", "")
                    issuer = dict(cert.get("issuer", [])).get("organizationName")
                    days = None
                    valid_from = None
                    valid_to = None

                    try:
                        expiry = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                        expiry = expiry.replace(tzinfo=timezone.utc)
                        now = datetime.now(timezone.utc)
                        days = (expiry - now).days
                        valid_to = expiry.isoformat()
                    except (ValueError, TypeError):
                        pass

                    try:
                        start = datetime.strptime(not_before, "%b %d %H:%M:%S %Y %Z")
                        start = start.replace(tzinfo=timezone.utc)
                        valid_from = start.isoformat()
                    except (ValueError, TypeError):
                        pass

                    return (days, issuer, valid_from, valid_to)

        except (socket.timeout, socket.error, ssl.SSLError, OSError):
            return (None, None, None, None)
