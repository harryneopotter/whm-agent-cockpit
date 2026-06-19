"""Base collector pattern — all collectors inherit from this."""

from __future__ import annotations

import abc
import json
import logging
import sqlite3
import time
from typing import Any

from cockpit.config import settings

logger = logging.getLogger(__name__)


class CollectorError(Exception):
    """Raised when a collector run fails."""


class BaseCollector(abc.ABC):
    """Every collector polls a source and writes structured data to SQLite.

    Subclasses implement poll() to return a dict of {table: [row_dicts, ...]}.
    Rows must include a 'collected_at' field (ISO-8601), plus any TTL / freshness info.
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or settings.db_path

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Short identifier, e.g. 'server_health'."""

    @abc.abstractmethod
    async def poll(self) -> dict[str, list[dict[str, Any]]]:
        """Collect fresh data. Return {table_name: [rows]}."""

    async def run(self) -> None:
        """Collect and persist. Logs on failure; does NOT raise."""
        try:
            data = await self.poll()
            self._store(data)
            logger.info("%s: collected %d tables", self.name, len(data))
        except Exception:
            logger.exception("%s: collection failed", self.name)

    def _store(self, data: dict[str, list[dict[str, Any]]]) -> None:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        try:
            for table, rows in data.items():
                if not rows:
                    continue
                self._upsert_many(conn, table, rows)
            conn.commit()
        finally:
            conn.close()

    def _upsert_many(
        self, conn: sqlite3.Connection, table: str, rows: list[dict[str, Any]]
    ) -> None:
        if not rows:
            return
        columns = list(rows[0].keys())
        placeholders = ", ".join("?" for _ in columns)
        col_list = ", ".join(columns)
        # Build update_set for UPSERT: SET col_i=excluded.col_i for non-pk columns
        pk_cols = self._pk_columns(conn, table)
        update_set = ", ".join(
            f"{c}=excluded.{c}" for c in columns if c not in pk_cols
        )

        sql = (
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT({', '.join(pk_cols)}) DO UPDATE SET {update_set}"
            if pk_cols and update_set
            else f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
        )

        batch = [[row.get(c) for c in columns] for row in rows]
        conn.executemany(sql, batch)

    @staticmethod
    def _pk_columns(conn: sqlite3.Connection, table: str) -> list[str]:
        cursor = conn.execute(f"PRAGMA table_info({table});")
        return [row[1] for row in cursor.fetchall() if row[5] == 1]  # pk flag

    @staticmethod
    def now_iso() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    @staticmethod
    def freshness_status(collected_at: str, ttl_seconds: int) -> str:
        import datetime
        try:
            dt = datetime.datetime.fromisoformat(collected_at)
            age = (datetime.datetime.now(dt.tzinfo) - dt).total_seconds()
        except Exception:
            return "unknown"
        if age < ttl_seconds:
            return "fresh"
        if age < ttl_seconds * 2:
            return "stale"
        return "unknown"
