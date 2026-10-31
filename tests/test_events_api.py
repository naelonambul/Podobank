from __future__ import annotations

import base64
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import UTC, datetime
from threading import Event as ThreadEvent
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from podobank.db import Database, Event

PARTNER_ID = "shop-simulator"
PARTNER_KEY = "test-partner-secret"


def make_client(database_url: str) -> TestClient:
    try:
        module_spec = importlib.util.find_spec("podobank.main")
    except ModuleNotFoundError:
        module_spec = None
    assert module_spec is not None, "The Podobank FastAPI application must be implemented."

    from podobank.config import Settings
    from podobank.main import create_app

    settings = Settings(database_url=database_url, partner_keys={PARTNER_ID: PARTNER_KEY})
    return TestClient(create_app(database_url=database_url, settings=settings))


def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {PARTNER_KEY}"}


def seed_payload(sandbox_id: str, customer_count: int = 2) -> dict[str, Any]:
    return {"sandboxId": sandbox_id, "customerCount": customer_count, "merchantCount": 1}


def make_event(event_id: str) -> Event:
    now = datetime.now(UTC)
    return Event(
        event_id=event_id,
        schema_version=1,
        event_type="deposit.completed",
        occurred_at=now,
        recorded_at=now,
        correlation_id=str(uuid4()),
        entity_refs={"accountId": str(uuid4())},
        data={"amountWon": 100, "currency": "KRW"},
    )


def append_event(database_url: str, started: ThreadEvent, event_id: str) -> Event:
    database = Database(database_url)
    try:
        started.set()
        with database.transaction() as connection:
            return database.events.append(connection, make_event(event_id))
    finally:
        database.dispose()


def test_event_envelope_filters_and_cursor_order(database_url: str) -> None:
    with make_client(database_url) as client:
        seed = client.post(
            "/v1/sandbox/seed", json=seed_payload("event-filter-seed"), headers=auth_headers()
        ).json()
        correlation_id = seed["correlationId"]
        response = client.get(
            "/v1/events",
            params={"eventType": "customer.created", "correlationId": correlation_id, "limit": 1},
            headers=auth_headers(),
        )
        first_page = response.json()
        next_page = client.get(
            "/v1/events",
            params={"cursor": first_page["nextCursor"], "limit": 1},
            headers=auth_headers(),
        ).json()

    assert response.status_code == 200
    assert len(first_page["items"]) == 1
    assert first_page["nextCursor"]
    assert first_page["highWaterSequence"] >= first_page["items"][0]["sequence"]
    assert next_page["items"][0]["eventType"] == "customer.created"
    event = first_page["items"][0]
    assert event["eventId"]
    assert event["schemaVersion"] == 1
    assert event["correlationId"] == correlation_id
    assert event["occurredAt"].endswith("Z")
    assert event["recordedAt"].endswith("Z")
    assert event["data"]["simulation"] is True
    assert "customerId" in event["entityRefs"]


def test_entity_and_time_filters_select_matching_events(database_url: str) -> None:
    with make_client(database_url) as client:
        matching_seed = client.post(
            "/v1/sandbox/seed", json=seed_payload("entity-time-match"), headers=auth_headers()
        ).json()
        client.post(
            "/v1/sandbox/seed", json=seed_payload("entity-time-other"), headers=auth_headers()
        )
        response = client.get(
            "/v1/events",
            params={
                "entityId": matching_seed["customers"][0]["customerId"],
                "from": "2000-01-01T00:00:00Z",
                "to": "2100-01-01T00:00:00Z",
                "limit": 100,
            },
            headers=auth_headers(),
        )

    assert response.status_code == 200
    assert response.json()["items"]
    assert all(
        matching_seed["customers"][0]["customerId"] in event["entityRefs"].values()
        for event in response.json()["items"]
    )


def test_high_water_cursor_excludes_appends_after_first_page(database_url: str) -> None:
    with make_client(database_url) as client:
        original = client.post(
            "/v1/sandbox/seed", json=seed_payload("cursor-original"), headers=auth_headers()
        ).json()
        first_page = client.get(
            "/v1/events",
            params={"correlationId": original["correlationId"], "limit": 1},
            headers=auth_headers(),
        ).json()
        appended = client.post(
            "/v1/sandbox/seed", json=seed_payload("cursor-appended"), headers=auth_headers()
        ).json()

        original_events = list(first_page["items"])
        cursor = first_page["nextCursor"]
        while cursor:
            page = client.get(
                "/v1/events", params={"cursor": cursor, "limit": 1}, headers=auth_headers()
            ).json()
            original_events.extend(page["items"])
            cursor = page["nextCursor"]

    original_ids = {customer["customerId"] for customer in original["customers"]}
    appended_ids = {customer["customerId"] for customer in appended["customers"]}
    event_ids = [event["eventId"] for event in original_events]
    assert len(event_ids) == len(set(event_ids))
    assert all(event["sequence"] <= first_page["highWaterSequence"] for event in original_events)
    assert all(
        set(event["entityRefs"].values()).isdisjoint(appended_ids) for event in original_events
    )
    assert any(
        set(event["entityRefs"].values()).intersection(original_ids) for event in original_events
    )


def test_cursor_rejects_changed_filters_and_malformed_values(database_url: str) -> None:
    with make_client(database_url) as client:
        client.post(
            "/v1/sandbox/seed", json=seed_payload("cursor-filter-seed"), headers=auth_headers()
        )
        first = client.get(
            "/v1/events",
            params={"eventType": "customer.created", "limit": 1},
            headers=auth_headers(),
        ).json()
        changed = client.get(
            "/v1/events",
            params={"eventType": "account.opened", "cursor": first["nextCursor"], "limit": 1},
            headers=auth_headers(),
        )
        malformed = client.get(
            "/v1/events", params={"cursor": "not-a-cursor"}, headers=auth_headers()
        )
        negative_sequence_cursor = base64.urlsafe_b64encode(
            json.dumps(
                {
                    "afterSequence": -1,
                    "highWaterSequence": 0,
                    "limit": 1,
                    "filters": {
                        "eventType": None,
                        "entityId": None,
                        "correlationId": None,
                        "from": None,
                        "to": None,
                    },
                }
            ).encode()
        ).decode()
        invalid_bounds = client.get(
            "/v1/events",
            params={"cursor": negative_sequence_cursor},
            headers=auth_headers(),
        )

    assert changed.status_code == 400
    assert changed.json()["error"]["code"] == "invalid_cursor"
    assert malformed.status_code == 400
    assert malformed.json()["error"]["code"] == "invalid_cursor"
    assert invalid_bounds.status_code == 400
    assert invalid_bounds.json()["error"]["code"] == "invalid_cursor"


def test_event_sequences_wait_for_prior_transaction_commit(database_url: str) -> None:
    database = Database(database_url)
    database.initialize_schema()
    first_connection = database.engine.connect()
    first_transaction = first_connection.begin()
    first = database.events.append(first_connection, make_event(str(uuid4())))
    started = ThreadEvent()
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            second_future = executor.submit(append_event, database_url, started, str(uuid4()))
            assert started.wait(timeout=2)
            with pytest.raises(TimeoutError):
                second_future.result(timeout=0.2)

            first_transaction.commit()
            first_connection.close()
            second = second_future.result(timeout=5)

        assert first.sequence is not None
        assert second.sequence is not None
        assert first.sequence < second.sequence
    finally:
        if first_transaction.is_active:
            first_transaction.rollback()
        first_connection.close()
        database.dispose()
