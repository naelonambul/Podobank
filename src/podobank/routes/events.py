"""Append-only business event polling endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from podobank.auth import authenticate_request
from podobank.events import InvalidCursor, event_payload, list_event_page

router = APIRouter(prefix="/v1/events", tags=["Events"])


@router.get(
    "",
    summary="Poll synthetic business events",
    description=(
        "Read events in sequence order. The first page captures a high-water sequence; "
        "continue with its cursor to traverse that stable event view."
    ),
)
def get_events(
    request: Request,
    partner_id: Annotated[str, Depends(authenticate_request)],
    event_type: Annotated[
        str | None, Query(alias="eventType", min_length=1, max_length=120)
    ] = None,
    entity_id: Annotated[str | None, Query(alias="entityId", min_length=1, max_length=80)] = None,
    correlation_id: Annotated[
        str | None, Query(alias="correlationId", min_length=1, max_length=80)
    ] = None,
    occurred_from: Annotated[datetime | None, Query(alias="from")] = None,
    occurred_to: Annotated[datetime | None, Query(alias="to")] = None,
    cursor: Annotated[str | None, Query(min_length=1, max_length=2048)] = None,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
) -> dict[str, Any]:
    del partner_id
    if occurred_from is not None and occurred_to is not None and occurred_from >= occurred_to:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_request",
                "message": "The from timestamp must be earlier than the to timestamp.",
            },
        )

    database = request.app.state.database
    try:
        with database.engine.connect() as connection:
            page = list_event_page(
                database,
                connection,
                event_type=event_type,
                entity_id=entity_id,
                correlation_id=correlation_id,
                occurred_from=occurred_from,
                occurred_to=occurred_to,
                cursor=cursor,
                limit=limit,
            )
    except InvalidCursor as error:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_cursor", "message": str(error)},
        ) from error

    return {
        "items": [event_payload(event) for event in page.items],
        "nextCursor": page.next_cursor,
        "highWaterSequence": page.high_water_sequence,
    }
