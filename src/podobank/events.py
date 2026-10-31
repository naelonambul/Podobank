"""Business event creation, serialization, and stable cursor pagination."""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from podobank.db import Database, Event


class InvalidCursor(ValueError):
    """Raised when an event cursor is malformed or used with changed filters."""


@dataclass(frozen=True)
class EventPage:
    items: list[Event]
    next_cursor: str | None
    high_water_sequence: int


def append_event(
    database: Database,
    *,
    event_type: str,
    entity_refs: Mapping[str, str],
    correlation_id: str,
    data: Mapping[str, Any],
    connection: Connection | None = None,
    occurred_at: datetime | None = None,
    event_id: str | None = None,
) -> Event:
    now = datetime.now(UTC)
    event = Event(
        event_id=event_id or str(uuid4()),
        schema_version=1,
        event_type=event_type,
        occurred_at=occurred_at or now,
        recorded_at=now,
        correlation_id=correlation_id,
        entity_refs=dict(entity_refs),
        data=dict(data),
    )
    if connection is not None:
        return database.events.append(connection, event)
    with database.transaction() as own_connection:
        return database.events.append(own_connection, event)


def event_payload(event: Event) -> dict[str, Any]:
    return {
        "eventId": event.event_id,
        "schemaVersion": event.schema_version,
        "eventType": event.event_type,
        "occurredAt": _format_time(event.occurred_at),
        "recordedAt": _format_time(event.recorded_at),
        "correlationId": event.correlation_id,
        "entityRefs": event.entity_refs,
        "data": event.data,
        "sequence": event.sequence,
    }


def list_event_page(
    database: Database,
    connection: Connection,
    *,
    event_type: str | None,
    entity_id: str | None,
    correlation_id: str | None,
    occurred_from: datetime | None,
    occurred_to: datetime | None,
    cursor: str | None,
    limit: int | None,
) -> EventPage:
    requested_filters = _filter_payload(
        event_type, entity_id, correlation_id, occurred_from, occurred_to
    )
    if cursor is None:
        active_filters = requested_filters
        after_sequence = 0
        high_water_sequence = database.events.high_water(connection)
        page_limit = limit or 50
    else:
        cursor_payload = _decode_cursor(cursor)
        cursor_filters = cursor_payload.get("filters")
        if not isinstance(cursor_filters, dict):
            raise InvalidCursor("cursor filters are malformed")
        if any(value is not None for value in requested_filters.values()):
            if cursor_filters != requested_filters:
                raise InvalidCursor("cursor cannot be reused with different filters")
        active_filters = cursor_filters
        after_sequence = _cursor_integer(cursor_payload, "afterSequence")
        high_water_sequence = _cursor_integer(cursor_payload, "highWaterSequence")
        cursor_limit = _cursor_integer(cursor_payload, "limit")
        if limit is not None and limit != cursor_limit:
            raise InvalidCursor("cursor cannot be reused with a different page size")
        page_limit = cursor_limit
        if (
            after_sequence < 0
            or high_water_sequence < after_sequence
            or page_limit < 1
            or page_limit > 100
        ):
            raise InvalidCursor("cursor sequence bounds or page size are invalid")
        if high_water_sequence > database.events.high_water(connection):
            raise InvalidCursor("cursor high-water sequence is ahead of the event store")

    rows = database.events.list_after(
        connection,
        after_sequence=after_sequence,
        high_water_sequence=high_water_sequence,
        limit=page_limit + 1,
        event_type=_optional_string(active_filters, "eventType"),
        entity_id=_optional_string(active_filters, "entityId"),
        correlation_id=_optional_string(active_filters, "correlationId"),
        occurred_from=_parse_time(active_filters.get("from")),
        occurred_to=_parse_time(active_filters.get("to")),
    )
    has_more = len(rows) > page_limit
    items = rows[:page_limit]
    next_cursor: str | None = None
    if has_more and items[-1].sequence is not None:
        next_cursor = _encode_cursor(
            after_sequence=items[-1].sequence,
            high_water_sequence=high_water_sequence,
            limit=page_limit,
            filters=active_filters,
        )
    return EventPage(items, next_cursor, high_water_sequence)


def _filter_payload(
    event_type: str | None,
    entity_id: str | None,
    correlation_id: str | None,
    occurred_from: datetime | None,
    occurred_to: datetime | None,
) -> dict[str, str | None]:
    return {
        "eventType": event_type,
        "entityId": entity_id,
        "correlationId": correlation_id,
        "from": _format_time(occurred_from) if occurred_from is not None else None,
        "to": _format_time(occurred_to) if occurred_to is not None else None,
    }


def _format_time(value: datetime) -> str:
    normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return normalized.isoformat().replace("+00:00", "Z")


def _parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidCursor("cursor timestamp filter is malformed")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise InvalidCursor("cursor timestamp filter is malformed") from error
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _encode_cursor(
    *,
    after_sequence: int,
    high_water_sequence: int,
    limit: int,
    filters: Mapping[str, Any],
) -> str:
    payload = {
        "afterSequence": after_sequence,
        "highWaterSequence": high_water_sequence,
        "limit": limit,
        "filters": dict(filters),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> dict[str, Any]:
    try:
        raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        payload = json.loads(raw)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise InvalidCursor("cursor is malformed") from error
    if not isinstance(payload, dict):
        raise InvalidCursor("cursor is malformed")
    return payload


def _cursor_integer(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise InvalidCursor(f"cursor field {key} must be an integer")
    return value


def _optional_string(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidCursor(f"cursor field {key} must be a string")
    return value
