from __future__ import annotations

import importlib.util
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

PARTNER_ID = "shop-simulator"
PARTNER_KEY = "test-partner-secret"


def make_client(database_url: str) -> TestClient:
    try:
        module_spec = importlib.util.find_spec("podobank.main")
    except ModuleNotFoundError:
        module_spec = None
    assert module_spec is not None, "The Podobank scenario API must be implemented."

    from podobank.config import Settings
    from podobank.main import create_app

    settings = Settings(database_url=database_url, partner_keys={PARTNER_ID: PARTNER_KEY})
    return TestClient(create_app(database_url=database_url, settings=settings))


def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {PARTNER_KEY}"}


def test_scenario_reproduces_business_values_and_commits_events(database_url: str) -> None:
    sandbox_id = f"scenario-reproducible-{uuid4()}"
    payload = {"sandboxId": sandbox_id, "name": "baseline", "count": 5, "seed": 2468}
    with make_client(database_url) as client:
        first = client.post("/v1/sandbox/generations", json=payload, headers=auth_headers())
        second = client.post("/v1/sandbox/generations", json=payload, headers=auth_headers())
        event_response = client.get(
            "/v1/events",
            params={"correlationId": first.json()["correlationId"]},
            headers=auth_headers(),
        )

    assert first.status_code == second.status_code == 200
    first_result = first.json()
    second_result = second.json()

    def business_values(result: dict[str, Any]) -> list[tuple[str, int, int]]:
        return [
            (operation["operationType"], operation["amountWon"], operation["sourceIndex"])
            for operation in result["operations"]
        ]

    assert business_values(first_result) == business_values(second_result)
    assert first_result["seed"] == 2468
    assert len(first_result["operations"]) == 5
    assert all(operation["simulation"] is True for operation in first_result["operations"])
    assert all("anomaly" not in operation for operation in first_result["operations"])
    assert len(event_response.json()["items"]) == len(first_result["eventIds"])
    assert all(event["data"]["simulation"] is True for event in event_response.json()["items"])


def test_scenario_rejects_unknown_name_without_appending_events(database_url: str) -> None:
    with make_client(database_url) as client:
        before = client.get("/v1/events", headers=auth_headers()).json()["highWaterSequence"]
        response = client.post(
            "/v1/sandbox/generations",
            json={
                "sandboxId": f"scenario-invalid-{uuid4()}",
                "name": "fraud",
                "count": 2,
                "seed": 3,
            },
            headers=auth_headers(),
        )
        after = client.get("/v1/events", headers=auth_headers()).json()["highWaterSequence"]

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_scenario"
    assert before == after
