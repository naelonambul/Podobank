import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from podobank_api.features.client_events.mongodb import EventsUnavailable, store_event
from podobank_api.features.client_events.schemas import ClientEvent, EventTooLarge

router = APIRouter(tags=["client events"])
MAX_BODY_BYTES = 32768


def failure(status: int, code: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": {"code": code}})


@router.post("/events")
async def ingest_event(request: Request) -> JSONResponse:
    body = bytearray()
    try:
        declared_length = request.headers.get("content-length")
        if declared_length is not None:
            length = int(declared_length)
            if length < 0:
                return failure(422, "invalid_event")
            if length > MAX_BODY_BYTES:
                raise EventTooLarge
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_BODY_BYTES:
                raise EventTooLarge
            body.extend(chunk)
        event = ClientEvent.model_validate(json.loads(body))
    except EventTooLarge:
        return failure(413, "event_too_large")
    except (ValidationError, ValueError, UnicodeError, RecursionError):
        return failure(422, "invalid_event")
    try:
        result = await run_in_threadpool(store_event, event)
    except EventsUnavailable:
        return failure(503, "events_unavailable")
    return JSONResponse(status_code=201 if result == "stored" else 200, content={"status": result})
