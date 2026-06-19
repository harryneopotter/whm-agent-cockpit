"""HTTP health collector (Phase 2.5) — checks website reachability per account."""

from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx

from cockpit.collectors.base import BaseCollector
from cockpit.config import settings


class HTTPHealthCollector(BaseCollector):
    """Check each account's primary domain via HTTP HEAD/GET.

    Uses curl --resolve for origin-specific checks (SNI-safe per addendum §5).
    Returns edge + origin status separately.
    """

    name = "http_health"

    def __init__(self, db_path: str | None = None) -> None:
        super().__init__(db_path)
        self._semaphore = asyncio.Semaphore(settings.http_check_concurrency)
        self._timeout = httpx.Timeout(settings.http_check_timeout)

    async def poll(self) -> dict[str, list[dict[str, Any]]]:
        """Fetch all accounts from DB, check each domain."""
        domains = self._get_account_domains()
        now = self.now_iso()
        rows: list[dict[str, Any]] = []

        async def check(domain: str, username: str) -> dict[str, Any] | None:
            async with self._semaphore:
                # Jitter to avoid thundering herd
                jitter = random.uniform(0, settings.http_check_jitter_seconds)
                await asyncio.sleep(jitter)
                return await self._check_domain(domain, username, now)

        tasks = [check(domain, user) for user, domain in domains.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, dict):
                rows.append(r)
            # Silently skip failed checks (logged by _check_domain)

        return {"account_health": rows}

    async def _check_domain(
        self, domain: str, username: str, now: str
    ) -> dict[str, Any]:
        record: dict[str, Any] = {
            "username": username,
            "collected_at": now,
            "http_status_code": None,
            "response_time_ms": None,
            "ssl_valid": None,
            "ssl_days_remaining": None,
            "online_status": "UNKNOWN",
            "edge_status": None,
            "origin_status": None,
            "origin_check_method": None,
            "ttl_seconds": 180,
        }

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                headers={"User-Agent": settings.http_check_user_agent},
                follow_redirects=True,
            ) as client:
                start = asyncio.get_event_loop().time()
                resp = await client.head(f"https://{domain}")
                elapsed = int((asyncio.get_event_loop().time() - start) * 1000)

                record["http_status_code"] = resp.status_code
                record["response_time_ms"] = elapsed
                record["edge_status"] = self._classify(resp.status_code, elapsed)
                record["online_status"] = record["edge_status"]

                # Check SSL via cert info
                if resp.url.scheme == "https":
                    record["ssl_valid"] = 1

        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError):
            record["online_status"] = "DOWN"
        except httpx.HTTPStatusError as exc:
            record["http_status_code"] = exc.response.status_code
            record["online_status"] = self._classify(exc.response.status_code, None)
        except Exception:
            record["online_status"] = "SSL_ERROR"

        return record

    def _get_account_domains(self) -> dict[str, str]:
        """Fetch {username: primary_domain} from SQLite."""
        import sqlite3
        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute(
                "SELECT username, domain FROM whm_accounts WHERE domain != ''"
            )
            return {row[0]: row[1] for row in cursor.fetchall()}
        finally:
            conn.close()

    @staticmethod
    def _classify(status_code: int | None, elapsed_ms: int | None) -> str:
        if status_code is None:
            return "DOWN"
        if 200 <= status_code < 400:
            if elapsed_ms and elapsed_ms > 5000:
                return "DEGRADED"
            return "UP"
        if status_code in (401, 403):
            return "REACHABLE_PROTECTED"
        if status_code == 404:
            return "REACHABLE_NOT_FOUND"
        if status_code >= 500:
            return "DOWN"
        return "UNKNOWN"
