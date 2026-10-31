from __future__ import annotations

import importlib.util
import json
from typing import Any

from fastapi.testclient import TestClient

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


def test_seed_requires_partner_authentication(database_url: str) -> None:
    with make_client(database_url) as client:
        response = client.post("/v1/sandbox/seed", json=seed_payload("unauthenticated"))
        event_response = client.get("/v1/events")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert event_response.status_code == 401
    assert event_response.json()["error"]["code"] == "unauthorized"


def test_seed_reuses_synthetic_data_without_exposing_partner_secret(database_url: str) -> None:
    with make_client(database_url) as client:
        first = client.post(
            "/v1/sandbox/seed", json=seed_payload("reusable-seed"), headers=auth_headers()
        )
        second = client.post(
            "/v1/sandbox/seed", json=seed_payload("reusable-seed"), headers=auth_headers()
        )
        events = client.get(
            "/v1/events",
            params={
                "eventType": "customer.created",
                "correlationId": first.json()["correlationId"],
                "limit": 50,
            },
            headers=auth_headers(),
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert len(first.json()["customers"]) == 2
    assert len(first.json()["merchants"]) == 1
    assert PARTNER_KEY not in json.dumps(first.json())
    assert PARTNER_KEY not in json.dumps(events.json())
    assert len(events.json()["items"]) == 2
    assert all(event["data"]["simulation"] is True for event in events.json()["items"])


def test_seed_validation_rejects_invalid_counts_without_events(database_url: str) -> None:
    with make_client(database_url) as client:
        before = client.get("/v1/events", params={"limit": 1}, headers=auth_headers()).json()
        invalid = client.post(
            "/v1/sandbox/seed",
            json={"sandboxId": "invalid-seed", "customerCount": 0, "merchantCount": 1},
            headers=auth_headers(),
        )
        after = client.get("/v1/events", params={"limit": 1}, headers=auth_headers()).json()

    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "invalid_request"
    assert after["highWaterSequence"] == before["highWaterSequence"]
