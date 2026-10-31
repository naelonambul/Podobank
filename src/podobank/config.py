"""Environment-backed application settings."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    database_url: str
    partner_keys: dict[str, str] = field(default_factory=dict)
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

        partner_keys_raw = os.environ.get("PODOBANK_PARTNER_KEYS", "{}")
        try:
            partner_keys_value = json.loads(partner_keys_raw)
        except json.JSONDecodeError as error:
            raise ValueError("PODOBANK_PARTNER_KEYS must be a JSON object") from error
        if not isinstance(partner_keys_value, dict) or any(
            not isinstance(partner_id, str)
            or not partner_id
            or not isinstance(partner_key, str)
            or not partner_key
            for partner_id, partner_key in partner_keys_value.items()
        ):
            raise ValueError("PODOBANK_PARTNER_KEYS must map non-empty partner IDs to keys")

        return cls(
            database_url=database_url,
            partner_keys=partner_keys_value,
            event_log_path=os.environ.get(
                "PODOBANK_EVENT_LOG_PATH", "/var/log/podobank/events.ndjson"
            ),
            environment=os.environ.get("PODOBANK_ENVIRONMENT", "local"),
        )
