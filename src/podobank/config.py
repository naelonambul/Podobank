"""Environment-backed application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    event_log_path: str = "/var/log/podobank/events.ndjson"
    environment: str = "local"

    @classmethod
    def from_environment(cls) -> Settings:
        database_url = os.environ.get("PODOBANK_DATABASE_URL")
        if not database_url:
            user = os.environ.get("PODOBANK_DB_USER", "podobank")
            password = os.environ.get("PODOBANK_DB_PASSWORD")
            database = os.environ.get("PODOBANK_DB_NAME", "podobank")
            host = os.environ.get("PODOBANK_DB_HOST", "127.0.0.1")
            port = os.environ.get("PODOBANK_DB_PORT", "3306")
            if not password:
                raise ValueError("PODOBANK_DATABASE_URL or PODOBANK_DB_PASSWORD is required")
            database_url = (
                f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"
            )

        return cls(
            database_url=database_url,
            event_log_path=os.environ.get(
                "PODOBANK_EVENT_LOG_PATH", "/var/log/podobank/events.ndjson"
            ),
            environment=os.environ.get("PODOBANK_ENVIRONMENT", "local"),
        )
