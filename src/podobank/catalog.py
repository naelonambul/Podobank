"""Versioned loan-product snapshots and stable catalog pagination."""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import Connection

from podobank.db import Database


class InvalidProductCursor(ValueError):
    """Raised when a loan-product cursor is malformed or its filters changed."""


@dataclass(frozen=True)
class ProductSnapshot:
    product_ref: str
    institution_name: str
    product_name: str
    product_category: str
    facts: dict[str, Any]
    source_url: str
    retrieved_at: datetime
    effective_date: date | None
    source_status: str = "active"
    snapshot_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")
        if self.source_status not in {"active", "retired"}:
            raise ValueError("source_status must be active or retired")


@dataclass(frozen=True)
class ProductPage:
    items: list[dict[str, Any]]
    next_cursor: str | None
    high_water_created_at: datetime | None


def read_product_page(
    database: Database,
    connection: Connection,
    *,
    product_ref: str | None,
    institution_name: str | None,
    include_history: bool | None,
    cursor: str | None,
    limit: int | None,
    freshness_interval_seconds: int = 604800,
) -> ProductPage:
    requested_filters: dict[str, Any] = {
        "productRef": product_ref,
        "institutionName": institution_name,
        "includeHistory": include_history,
    }
    if cursor is None:
        active_filters = {
            "productRef": product_ref,
            "institutionName": institution_name,
            "includeHistory": include_history if include_history is not None else False,
        }
        after_created_at = None
        after_snapshot_id = None
        database.catalog_snapshots.acquire_writer_lock(connection)
        high_water = database.catalog_snapshots.latest_created_at(connection)
        page_limit = limit or 50
    else:
        payload = _decode_cursor(cursor)
        filters = payload.get("filters")
        if not isinstance(filters, dict) or set(filters) != {
            "productRef",
            "institutionName",
            "includeHistory",
        }:
            raise InvalidProductCursor("cursor filters are malformed")
        for key, requested_value in requested_filters.items():
            if requested_value is not None and filters.get(key) != requested_value:
                raise InvalidProductCursor("cursor cannot be reused with different filters")
        if not isinstance(filters["includeHistory"], bool):
            raise InvalidProductCursor("cursor history filter is malformed")
        if any(
            value is not None and not isinstance(value, str)
            for key, value in filters.items()
            if key != "includeHistory"
        ):
            raise InvalidProductCursor("cursor text filters are malformed")
        active_filters = filters
        after_created_at = _cursor_timestamp(payload, "afterCreatedAt")
        after_snapshot_id = _cursor_text(payload, "afterSnapshotId")
        high_water = _cursor_timestamp(payload, "highWaterCreatedAt")
        page_limit = _cursor_integer(payload, "limit")
        if high_water is None or after_created_at is None or after_snapshot_id is None:
            raise InvalidProductCursor("cursor bounds are incomplete")
        current_high_water = database.catalog_snapshots.latest_created_at(connection)
        if current_high_water is None or high_water > current_high_water:
            raise InvalidProductCursor("cursor high-water timestamp is ahead of the catalog")
        if after_created_at > high_water or page_limit < 1 or page_limit > 100:
            raise InvalidProductCursor("cursor bounds or page size are invalid")
        if limit is not None and limit != page_limit:
            raise InvalidProductCursor("cursor cannot be reused with a different page size")

    if high_water is None:
        return ProductPage([], None, None)
    rows = database.catalog_snapshots.list_page(
        connection,
        high_water_created_at=high_water,
        after_created_at=after_created_at,
        after_snapshot_id=after_snapshot_id,
        limit=page_limit + 1,
        product_ref=cast(str | None, active_filters["productRef"]),
        institution_name=cast(str | None, active_filters["institutionName"]),
        include_history=cast(bool, active_filters["includeHistory"]),
    )
    has_more = len(rows) > page_limit
    items = rows[:page_limit]
    next_cursor = None
    if has_more:
        last = items[-1]
        next_cursor = _encode_cursor(
            filters=active_filters,
            limit=page_limit,
            high_water_created_at=high_water,
            after_created_at=last["created_at"],
            after_snapshot_id=last["snapshot_id"],
        )
    freshness_by_source: dict[str, str] = {}
    payloads: list[dict[str, Any]] = []
    for row in items:
        institution_id = str(row["product_ref"]).partition(":")[0]
        if institution_id not in freshness_by_source:
            health = database.catalog_refresh_state.health(connection, institution_id)
            if health is None or health["last_completed_at"] is None:
                freshness = "unknown"
            elif health["last_error"] is not None or (
                datetime.now(UTC) - health["last_completed_at"]
                > timedelta(seconds=freshness_interval_seconds)
            ):
                freshness = "stale"
            else:
                freshness = "current"
            freshness_by_source[institution_id] = freshness
        payloads.append(product_payload(row, source_freshness=freshness_by_source[institution_id]))
    return ProductPage(payloads, next_cursor, high_water)


def product_payload(
    snapshot: Mapping[str, Any], *, source_freshness: str = "unknown"
) -> dict[str, Any]:
    effective_date = snapshot["effective_date"]
    facts = snapshot["facts"]
    return {
        "snapshotId": snapshot["snapshot_id"],
        "productRef": snapshot["product_ref"],
        "institutionName": snapshot["institution_name"],
        "productName": snapshot["product_name"],
        "productCategory": snapshot["product_category"],
        "facts": facts,
        "factAvailability": {
            key: "unknown" if value is None or value == [] else "published"
            for key, value in facts.items()
        },
        "sourceUrl": snapshot["source_url"],
        "retrievedAt": _format_time(snapshot["retrieved_at"]),
        "effectiveDate": effective_date.isoformat() if effective_date is not None else None,
        "sourceStatus": snapshot["source_status"],
        "sourceFreshness": source_freshness,
    }


def _format_time(value: datetime) -> str:
    normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return normalized.isoformat().replace("+00:00", "Z")


def _encode_cursor(
    *,
    filters: Mapping[str, Any],
    limit: int,
    high_water_created_at: datetime,
    after_created_at: datetime,
    after_snapshot_id: str,
) -> str:
    payload = {
        "filters": dict(filters),
        "limit": limit,
        "highWaterCreatedAt": _format_time(high_water_created_at),
        "afterCreatedAt": _format_time(after_created_at),
        "afterSnapshotId": after_snapshot_id,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> dict[str, Any]:
    try:
        raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        payload = json.loads(raw)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise InvalidProductCursor("cursor is malformed") from error
    if not isinstance(payload, dict):
        raise InvalidProductCursor("cursor is malformed")
    return payload


def _cursor_timestamp(payload: Mapping[str, Any], key: str) -> datetime | None:
    value = payload.get(key)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise InvalidProductCursor(f"cursor timestamp {key} is malformed") from error
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _cursor_text(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        return None
    return value


def _cursor_integer(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise InvalidProductCursor(f"cursor field {key} must be an integer")
    return value
