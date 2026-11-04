import json
import math
import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class EventTooLarge(Exception):
    pass


class EventPage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str
    referrer: str

    @field_validator("path", "referrer")
    @classmethod
    def bounded_url(cls, value: str) -> str:
        if len(value) > 2048:
            raise EventTooLarge
        return value

    @field_validator("path")
    @classmethod
    def clean_path(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//"):
            raise ValueError("invalid path")
        return urlsplit(value).path

    @field_validator("referrer")
    @classmethod
    def clean_referrer(cls, value: str) -> str:
        if not value:
            return ""
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("invalid referrer")
        host = parsed.hostname
        if ":" in host:
            host = f"[{host}]"
        if parsed.port:
            host += f":{parsed.port}"
        return urlunsplit((parsed.scheme, host, parsed.path or "/", "", ""))


class ClientEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    event_id: str
    type: str
    occurred_at: str
    session_id: str
    anonymous_id: str
    page: EventPage
    props: dict[str, object]
    schema_version: int

    @field_validator("event_id", "session_id", "anonymous_id")
    @classmethod
    def uuid_value(cls, value: str) -> str:
        return str(UUID(value))

    @field_validator("type")
    @classmethod
    def event_type(cls, value: str) -> str:
        if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value) is None:
            raise ValueError("invalid event type")
        return value

    @field_validator("occurred_at")
    @classmethod
    def utc_time(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            raise ValueError("UTC timestamp required")
        return parsed.isoformat().replace("+00:00", "Z")

    @field_validator("schema_version")
    @classmethod
    def supported_version(cls, value: int) -> int:
        if value != 4:
            raise ValueError("unsupported version")
        return value

    @field_validator("props")
    @classmethod
    def bounded_json(cls, value: dict[str, object]) -> dict[str, object]:
        keys = 0

        def visit(item: object, depth: int) -> None:
            nonlocal keys
            if isinstance(item, (dict, list)):
                if depth > 4:
                    raise ValueError("props nesting limit")
                if isinstance(item, dict):
                    keys += len(item)
                    if keys > 64 or any(not isinstance(key, str) for key in item):
                        raise ValueError("props key limit")
                    children = item.values()
                else:
                    children = item
                for child in children:
                    visit(child, depth + 1)
            elif type(item) not in (str, int, float, bool, type(None)):
                raise ValueError("JSON value required")
            elif isinstance(item, float) and not math.isfinite(item):
                raise ValueError("finite number required")

        visit(value, 1)
        if len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > 8192:
            raise EventTooLarge
        return value
