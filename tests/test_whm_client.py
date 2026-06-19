"""Tests for WHM API client."""

import pytest
from cockpit.whm_client import WHMAccount, _int_or_none


class TestIntOrNone:
    def test_int(self) -> None:
        assert _int_or_none(42) == 42

    def test_str_int(self) -> None:
        assert _int_or_none("42") == 42

    def test_none(self) -> None:
        assert _int_or_none(None) is None

    def test_invalid(self) -> None:
        assert _int_or_none("not a number") is None


class TestWHMAccount:
    def test_creation(self) -> None:
        acct = WHMAccount(
            username="testuser",
            domain="example.com",
            plan_name="Business",
            disk_used_mb=1024,
            disk_limit_mb=20480,
            bandwidth_used_mb=5000,
            bandwidth_limit_mb=102400,
            email_count=10,
            db_count=2,
            subdomain_count=1,
            addon_domain_count=1,
            parked_domain_count=0,
            php_version="8.2",
            suspended=False,
        )
        assert acct.username == "testuser"
        assert acct.domain == "example.com"
        assert not acct.suspended

    def test_suspended_flag(self) -> None:
        acct = WHMAccount(
            username="suspended_user",
            domain="suspended.com",
            plan_name=None,
            disk_used_mb=None,
            disk_limit_mb=None,
            bandwidth_used_mb=None,
            bandwidth_limit_mb=None,
            email_count=None,
            db_count=None,
            subdomain_count=None,
            addon_domain_count=None,
            parked_domain_count=None,
            php_version=None,
            suspended=True,
        )
        assert acct.suspended
