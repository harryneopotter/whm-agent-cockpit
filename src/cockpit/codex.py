"""Codex review pipeline (Phase 6).

Sends structured reports to OpenAI API and parses recommendations.
Codex is a reviewer only — no shell access, no command execution, no catalog modification.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any

import httpx

from cockpit.config import settings
from cockpit.reporting import ReportGenerator

logger = logging.getLogger(__name__)

CODEX_SYSTEM_PROMPT = """You are Codex, the Cockpit review AI.

You receive structured server reports and return recommendations.

Rules:
- You may recommend only action_ids from the available_action_ids list.
- You may NOT invent actions, write shell commands, or generate scripts.
- If a problem needs an action that doesn't exist, create a missing_action_request.
- Return valid JSON matching the output schema exactly.

Output schema:
{
  "reviewed_at": "...",
  "report_id": "...",
  "summary": "one-paragraph summary",
  "recommendations": [
    {
      "issue_id": "...",
      "priority": 1,
      "likely_cause": "...",
      "recommended_action_id": "ACTION_ID or null",
      "target": {},
      "confidence": "high|medium|low",
      "reason": "...",
      "approval_recommendation": "auto_run|auto_run_with_notification|approval_required|manual_only|null",
      "missing_action_request": { ... }  // optional
    }
  ]
}
"""

AVAILABLE_ACTION_IDS = [
    "RESTART_EXIM",
    "RESTART_DOVECOT",
    "RESTART_LITESPEED",
    "RUN_AUTOSSL_FOR_DOMAIN",
    "CHECK_SSL_FOR_DOMAIN",
    "CHECK_MAIL_HEALTH_FOR_DOMAIN",
    "REFRESH_BACKUP_STATUS",
    "CLEAR_LSCACHE_FOR_ACCOUNT",
    "GET_TOP_DISK_USERS",
    "CHECK_SERVICE_STATUS",
]


class CodexReviewer:
    """Sends reports to OpenAI and processes recommendations."""

    def __init__(self) -> None:
        self._report_gen = ReportGenerator()
        self._client = httpx.Client(timeout=60)

    def review(self, report_id: str | None = None) -> dict[str, Any]:
        """Generate a report, send to Codex, return recommendations."""
        report = self._report_gen.generate_report(report_id)
        report["available_action_ids"] = AVAILABLE_ACTION_IDS

        # Fetch previous failures from audit log
        report["previous_failed_actions"] = self._previous_failures()

        if not settings.openai_api_key:
            logger.warning("No OpenAI API key — returning empty Codex review")
            return {
                "reviewed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "report_id": report.get("report_id", ""),
                "summary": "Codex review skipped — no API key configured.",
                "recommendations": [],
            }

        return self._call_openai(report)

    def _call_openai(self, report: dict[str, Any]) -> dict[str, Any]:
        """Call OpenAI Chat Completions API."""
        try:
            resp = self._client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.openai_model,
                    "messages": [
                        {"role": "system", "content": CODEX_SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(report, indent=2)},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            result = json.loads(content)

            # Persist to DB
            self._save_review(report["report_id"], result)

            return result

        except Exception as exc:
            logger.exception("Codex review failed")
            return {
                "reviewed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "report_id": report.get("report_id", ""),
                "summary": f"Codex review failed: {exc}",
                "recommendations": [],
            }

    def _save_review(self, report_id: str, result: dict[str, Any]) -> None:
        conn = sqlite3.connect(settings.db_path)
        try:
            conn.execute(
                "INSERT INTO codex_reviews (report_id, reviewed_at, summary, recommendations) "
                "VALUES (?, ?, ?, ?)",
                (
                    report_id,
                    result.get("reviewed_at", ""),
                    result.get("summary", ""),
                    json.dumps(result.get("recommendations", [])),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _previous_failures() -> list[dict[str, Any]]:
        conn = sqlite3.connect(settings.db_path)
        try:
            rows = conn.execute(
                "SELECT data FROM audit_log WHERE event_type = 'action_failed' "
                "ORDER BY created_at DESC LIMIT 20"
            ).fetchall()
            return [json.loads(r["data"]) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()
