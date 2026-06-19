"""Application configuration — loaded from environment / .env file."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "COCKPIT_"}

    # Database
    db_path: str = "/var/lib/cockpit/cockpit.db"

    # WHM API
    whm_host: str = "localhost"
    whm_token: str = ""
    whm_port: int = 2087

    # Dashboard
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8080

    # Tailscale auth (enabled = trust Tailscale user identity from request headers)
    tailscale_auth_enabled: bool = True

    # Client Area API (Phase 2.5)
    client_api_key: str = ""
    client_api_host: str = "127.0.0.1"
    client_api_port: int = 8081

    # Scheduling
    collector_interval_critical_loop: int = 300  # 5 min
    collector_interval_stats: int = 600  # 10 min
    collector_interval_suspension: int = 60  # 60 sec
    collector_interval_http_health: int = 180  # 3 min

    # HTTP health check defaults (Phase 2.5)
    http_check_timeout: int = 15
    http_check_concurrency: int = 50
    http_check_jitter_seconds: int = 30
    http_check_user_agent: str = "BluePanda-Cockpit/1.0"
    http_check_retry: bool = True

    # Retention
    telemetry_retention_days: int = 14

    # Policy
    policy_path: str = "/etc/cockpit/policy.toml"

    # Codex
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    codex_report_interval_minutes: int = 720  # 12 hours


settings = Settings()
