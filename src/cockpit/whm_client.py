"""WHM API client — v1 API using token auth."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from cockpit.config import settings


class WHMError(Exception):
    """WHM API returned an error."""


@dataclass
class WHMAccount:
    """A single cPanel account from WHM API."""

    username: str
    domain: str
    plan_name: str | None
    disk_used_mb: int | None
    disk_limit_mb: int | None
    bandwidth_used_mb: int | None
    bandwidth_limit_mb: int | None
    email_count: int | None
    db_count: int | None
    subdomain_count: int | None
    addon_domain_count: int | None
    parked_domain_count: int | None
    php_version: str | None
    suspended: bool


class WHMClient:
    """Synchronous HTTP client for WHM API 1."""

    def __init__(
        self,
        host: str | None = None,
        token: str | None = None,
        port: int | None = None,
    ) -> None:
        self._host = host or settings.whm_host
        self._token = token or settings.whm_token
        self._port = port or settings.whm_port

        self._client = httpx.Client(
            base_url=f"https://{self._host}:{self._port}",
            verify=settings.whm_verify_ssl,
            timeout=30,
            headers={"Authorization": f"whm root:{self._token}"},
        )

    def _get(self, api_func: str, **params: Any) -> dict[str, Any]:
        resp = self._client.get(
            "/json-api/" + api_func,
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data.get("metadata"), dict) and data["metadata"].get("result") != 1:
            raise WHMError(data["metadata"].get("reason", "unknown WHM error"))
        return data

    def list_accounts(self) -> list[WHMAccount]:
        """Fetch every cPanel account via listaccts."""
        data = self._get("listaccts")
        accts: list[dict[str, Any]] = data.get("acct", [])
        result: list[WHMAccount] = []
        for a in accts:
            result.append(WHMAccount(
                username=a.get("user", ""),
                domain=a.get("domain", ""),
                plan_name=a.get("plan"),
                disk_used_mb=_int_or_none(a.get("diskused")),
                disk_limit_mb=_int_or_none(a.get("disklimit")),
                bandwidth_used_mb=_int_or_none(a.get("bandwidthused")),
                bandwidth_limit_mb=_int_or_none(a.get("bandwidthlimit")),
                email_count=_int_or_none(a.get("email_count")),
                db_count=_int_or_none(a.get("database_count")),
                subdomain_count=_int_or_none(a.get("subdomain_count")),
                addon_domain_count=_int_or_none(a.get("addon_domain_count")),
                parked_domain_count=_int_or_none(a.get("parked_domain_count")),
                php_version=a.get("phpversion"),
                suspended=a.get("suspended", 0) in (1, "1"),
            ))
        return result

    def account_summary(self, username: str) -> dict[str, Any]:
        """Fetch single account summary."""
        data = self._get("accountsummary", user=username)
        acct = data.get("acct", [{}])[0]
        return acct

    def close(self) -> None:
        self._client.close()


def _int_or_none(val: object) -> int | None:
    if val is None:
        return None
    try:
        return int(str(val))
    except (ValueError, TypeError):
        return None
