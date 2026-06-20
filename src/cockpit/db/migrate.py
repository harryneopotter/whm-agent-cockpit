"""Database schema migrations — SQLite."""

MIGRATIONS = [
    # V1: Initial schema
    """CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL DEFAULT (datetime('now'))
    );""",
    # V2: Core telemetry tables
    """CREATE TABLE IF NOT EXISTS server_health (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at TEXT NOT NULL,
        hostname TEXT NOT NULL,
        load_avg_1m REAL,
        load_avg_5m REAL,
        load_avg_15m REAL,
        cpu_percent REAL,
        ram_total_mb INTEGER,
        ram_used_mb INTEGER,
        ram_used_percent REAL,
        swap_total_mb INTEGER,
        swap_used_mb INTEGER,
        swap_used_percent REAL,
        uptime_seconds INTEGER,
        ttl_seconds INTEGER NOT NULL DEFAULT 60
    );""",
    """CREATE TABLE IF NOT EXISTS disk_health (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at TEXT NOT NULL,
        mount_point TEXT NOT NULL,
        total_gb REAL,
        used_gb REAL,
        free_gb REAL,
        used_percent REAL,
        inode_used_percent REAL,
        ttl_seconds INTEGER NOT NULL DEFAULT 120
    );""",
    """CREATE TABLE IF NOT EXISTS service_status (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at TEXT NOT NULL,
        service_name TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('running','stopped','unknown')),
        ttl_seconds INTEGER NOT NULL DEFAULT 120
    );""",
    """CREATE TABLE IF NOT EXISTS whm_accounts (
        username TEXT PRIMARY KEY,
        collected_at TEXT NOT NULL,
        domain TEXT NOT NULL,
        plan_name TEXT,
        disk_used_mb INTEGER,
        disk_limit_mb INTEGER,
        bandwidth_used_mb INTEGER,
        bandwidth_limit_mb INTEGER,
        email_count INTEGER,
        db_count INTEGER,
        subdomain_count INTEGER,
        addon_domain_count INTEGER,
        parked_domain_count INTEGER,
        php_version TEXT,
        suspended INTEGER NOT NULL DEFAULT 0,
        ttl_seconds INTEGER NOT NULL DEFAULT 600
    );""",
    # V3: Account/domain mapping
    """CREATE TABLE IF NOT EXISTS domain_mapping (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at TEXT NOT NULL,
        domain TEXT NOT NULL,
        username TEXT NOT NULL,
        domain_type TEXT NOT NULL CHECK(domain_type IN ('primary','addon','parked','subdomain')),
        ttl_seconds INTEGER NOT NULL DEFAULT 3600,
        FOREIGN KEY (username) REFERENCES whm_accounts(username)
    );""",
    # V4: SSL expiry
    """CREATE TABLE IF NOT EXISTS ssl_certs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at TEXT NOT NULL,
        domain TEXT NOT NULL,
        issuer TEXT,
        valid_from TEXT,
        valid_to TEXT,
        days_remaining INTEGER,
        auto_ssl_enabled INTEGER,
        ttl_seconds INTEGER NOT NULL DEFAULT 3600
    );""",
    # V5: Mail queue
    """CREATE TABLE IF NOT EXISTS mail_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at TEXT NOT NULL,
        queue_size INTEGER,
        frozen_count INTEGER,
        exim_errors_last_hour INTEGER,
        ttl_seconds INTEGER NOT NULL DEFAULT 120
    );""",
    # V6: JetBackup
    """CREATE TABLE IF NOT EXISTS jetbackup_status (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at TEXT NOT NULL,
        destination_reachable INTEGER,
        last_run_at TEXT,
        failed_accounts TEXT,
        accounts_missing_recent_backup TEXT,
        restore_point_counts TEXT,
        ttl_seconds INTEGER NOT NULL DEFAULT 600
    );""",
    # V7: LVE stats
    """CREATE TABLE IF NOT EXISTS lve_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collected_at TEXT NOT NULL,
        username TEXT NOT NULL,
        cpu_faults INTEGER,
        io_faults INTEGER,
        entry_process_faults INTEGER,
        memory_faults INTEGER,
        nproc_faults INTEGER,
        ttl_seconds INTEGER NOT NULL DEFAULT 300
    );""",
    # V8: Account stats (Phase 2.5)
    """CREATE TABLE IF NOT EXISTS account_stats (
        username TEXT PRIMARY KEY,
        collected_at TEXT NOT NULL,
        disk_used_mb INTEGER,
        disk_limit_mb INTEGER,
        bandwidth_used_mb INTEGER,
        bandwidth_limit_mb INTEGER,
        email_count INTEGER,
        db_count INTEGER,
        subdomain_count INTEGER,
        addon_domain_count INTEGER,
        parked_domain_count INTEGER,
        ftp_count INTEGER,
        plan_name TEXT,
        primary_ip TEXT,
        php_version TEXT,
        ttl_seconds INTEGER NOT NULL DEFAULT 600
    );""",
    # V9: Suspension status (fast-path)
    """CREATE TABLE IF NOT EXISTS suspension_status (
        username TEXT PRIMARY KEY,
        collected_at TEXT NOT NULL,
        suspended INTEGER NOT NULL DEFAULT 0,
        ttl_seconds INTEGER NOT NULL DEFAULT 60
    );""",
    # V10: Account HTTP health (Phase 2.5)
    """CREATE TABLE IF NOT EXISTS account_health (
        username TEXT PRIMARY KEY,
        collected_at TEXT NOT NULL,
        http_status_code INTEGER,
        response_time_ms INTEGER,
        ssl_valid INTEGER,
        ssl_days_remaining INTEGER,
        online_status TEXT NOT NULL DEFAULT 'UNKNOWN'
            CHECK(online_status IN ('UP','REACHABLE_PROTECTED','REACHABLE_NOT_FOUND','DEGRADED','DOWN','SSL_ERROR','UNKNOWN')),
        edge_status TEXT,
        origin_status TEXT,
        origin_check_method TEXT,
        ttl_seconds INTEGER NOT NULL DEFAULT 180
    );""",
    # V11: Issues / alerts
    """CREATE TABLE IF NOT EXISTS issues (
        issue_id TEXT PRIMARY KEY,
        detected_at TEXT NOT NULL,
        acknowledged_at TEXT,
        resolved_at TEXT,
        severity TEXT NOT NULL CHECK(severity IN ('critical','warning','info')),
        state TEXT NOT NULL DEFAULT 'NEW'
            CHECK(state IN ('NEW','ACKNOWLEDGED','AUTO_FIX_ELIGIBLE','PENDING_APPROVAL',
                            'FIX_RUNNING','POST_CHECK_RUNNING','RESOLVED','FAILED',
                            'ESCALATED_TO_WHM','SUPPRESSED')),
        description TEXT NOT NULL,
        consecutive_detections INTEGER NOT NULL DEFAULT 1,
        target_type TEXT,
        target_id TEXT,
        ttl_seconds INTEGER NOT NULL DEFAULT 86400
    );""",
    # V12: Audit log
    """CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        event_type TEXT NOT NULL,
        source TEXT NOT NULL,
        data TEXT NOT NULL
    );""",
    # V13: Action catalog (runtime cache of policy-known actions)
    """CREATE TABLE IF NOT EXISTS action_catalog (
        action_id TEXT PRIMARY KEY,
        risk_tier INTEGER NOT NULL CHECK(risk_tier IN (0,1,2,3)),
        description TEXT NOT NULL,
        target_type TEXT,
        approval_required INTEGER NOT NULL DEFAULT 0,
        cooldown_seconds INTEGER NOT NULL DEFAULT 0,
        enabled INTEGER NOT NULL DEFAULT 1
    );""",
    # V14: Codex review recommendations
    """CREATE TABLE IF NOT EXISTS codex_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id TEXT NOT NULL,
        reviewed_at TEXT NOT NULL,
        summary TEXT,
        recommendations TEXT NOT NULL
    );""",
    # V15: Missing-action requests
    """CREATE TABLE IF NOT EXISTS missing_action_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        pattern TEXT NOT NULL,
        suggested_action_name TEXT,
        why_insufficient TEXT,
        risk_level TEXT,
        status TEXT NOT NULL DEFAULT 'open'
            CHECK(status IN ('open','reviewed','implemented','rejected'))
    );""",
]


def main() -> None:
    """Apply all pending migrations."""
    import sqlite3
    import os

    db_path = os.environ.get("COCKPIT_DB_PATH", "/var/lib/cockpit/cockpit.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    # Get current version
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "  version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ");"
    )
    row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version;").fetchone()
    current_version = row[0]

    for i, sql in enumerate(MIGRATIONS, start=1):
        if i > current_version:
            print(f"  Applying migration V{i}...")
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?);", (i,)
            )
            conn.commit()

    conn.close()
    print(f"Schema at version {len(MIGRATIONS)}.")


if __name__ == "__main__":
    main()
