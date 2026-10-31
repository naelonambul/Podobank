from __future__ import annotations

import importlib.util
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from podobank.db import Database
from podobank.ledger import Ledger

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


def auth_headers(key: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {key or PARTNER_KEY}"}


def seed_accounts(client: TestClient, sandbox_id: str) -> list[dict[str, str]]:
    response = client.post(
        "/v1/sandbox/seed",
        json={"sandboxId": sandbox_id, "customerCount": 2, "merchantCount": 1},
        headers=auth_headers(),
    )
    assert response.status_code == 200
    return response.json()["customers"]


def test_deposit_withdrawal_and_transfer_update_balances_and_events(database_url: str) -> None:
    with make_client(database_url) as client:
        accounts = seed_accounts(client, f"ledger-flow-{uuid4()}")
        source_id = accounts[0]["accountId"]
        destination_id = accounts[1]["accountId"]
        request_id = str(uuid4())

        deposit = client.post(
            f"/v1/accounts/{source_id}/deposits",
            json={"amountWon": 50_000},
            headers={**auth_headers(), "Idempotency-Key": f"deposit-{request_id}"},
        )
        withdrawal = client.post(
            f"/v1/accounts/{source_id}/withdrawals",
            json={"amountWon": 10_000},
            headers={**auth_headers(), "Idempotency-Key": f"withdrawal-{request_id}"},
        )
        transfer = client.post(
            "/v1/transfers",
            json={
                "sourceAccountId": source_id,
                "destinationAccountId": destination_id,
                "amountWon": 20_000,
            },
            headers={**auth_headers(), "Idempotency-Key": f"transfer-{request_id}"},
        )
        source = client.get(f"/v1/accounts/{source_id}", headers=auth_headers()).json()
        destination = client.get(f"/v1/accounts/{destination_id}", headers=auth_headers()).json()

    assert deposit.status_code == 200
    assert withdrawal.status_code == 200
    assert transfer.status_code == 200
    assert source["balanceWon"] == 120_000
    assert destination["balanceWon"] == 145_000
    assert source["currency"] == destination["currency"] == "KRW"
    assert source["simulation"] is destination["simulation"] is True
    assert all(response.json()["eventIds"] for response in (deposit, withdrawal, transfer))
    assert transfer.json()["status"] == "completed"


def test_idempotency_replays_without_duplicate_events_and_conflicts_on_change(
    database_url: str,
) -> None:
    with make_client(database_url) as client:
        account = seed_accounts(client, f"ledger-idempotency-{uuid4()}")[0]["accountId"]
        headers = {**auth_headers(), "Idempotency-Key": f"deposit-replay-{uuid4()}"}
        first = client.post(
            f"/v1/accounts/{account}/deposits", json={"amountWon": 12_500}, headers=headers
        )
        replay = client.post(
            f"/v1/accounts/{account}/deposits", json={"amountWon": 12_500}, headers=headers
        )
        changed = client.post(
            f"/v1/accounts/{account}/deposits", json={"amountWon": 13_500}, headers=headers
        )
        events = client.get(
            "/v1/events",
            params={"correlationId": first.json()["correlationId"]},
            headers=auth_headers(),
        ).json()["items"]
        account_view = client.get(f"/v1/accounts/{account}", headers=auth_headers()).json()

    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "idempotency_conflict"
    assert len(events) == 1
    assert account_view["balanceWon"] == 112_500


@pytest.mark.parametrize("amount", [0, -1, 1.25, "100", 1 << 64])
def test_invalid_amounts_are_rejected_without_events_or_balance_changes(
    database_url: str, amount: Any
) -> None:
    with make_client(database_url) as client:
        account = seed_accounts(client, f"ledger-invalid-{uuid4()}")[0]["accountId"]
        before = client.get("/v1/events", headers=auth_headers()).json()["highWaterSequence"]
        response = client.post(
            f"/v1/accounts/{account}/deposits",
            json={"amountWon": amount},
            headers={**auth_headers(), "Idempotency-Key": f"invalid-amount-{uuid4()}"},
        )
        after = client.get("/v1/events", headers=auth_headers()).json()["highWaterSequence"]
        account_view = client.get(f"/v1/accounts/{account}", headers=auth_headers()).json()

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert before == after
    assert account_view["balanceWon"] == 100_000


def test_insufficient_funds_and_same_account_transfers_append_rejection_events(
    database_url: str,
) -> None:
    with make_client(database_url) as client:
        account = seed_accounts(client, f"ledger-rejections-{uuid4()}")[0]["accountId"]
        request_id = str(uuid4())
        initial_high_water = client.get("/v1/events", headers=auth_headers()).json()[
            "highWaterSequence"
        ]
        withdrawal = client.post(
            f"/v1/accounts/{account}/withdrawals",
            json={"amountWon": 100_001},
            headers={
                **auth_headers(),
                "Idempotency-Key": f"insufficient-withdrawal-{request_id}",
            },
        )
        same_account = client.post(
            "/v1/transfers",
            json={
                "sourceAccountId": account,
                "destinationAccountId": account,
                "amountWon": 1_000,
            },
            headers={**auth_headers(), "Idempotency-Key": f"same-account-transfer-{request_id}"},
        )
        final_high_water = client.get("/v1/events", headers=auth_headers()).json()[
            "highWaterSequence"
        ]
        account_view = client.get(f"/v1/accounts/{account}", headers=auth_headers()).json()
        rejections = client.get(
            "/v1/events",
            params={"eventType": "transaction.rejected", "entityId": account},
            headers=auth_headers(),
        ).json()["items"]

    assert withdrawal.status_code == 409
    assert withdrawal.json()["error"]["code"] == "insufficient_funds"
    assert same_account.status_code == 409
    assert same_account.json()["error"]["code"] == "same_account_transfer"
    assert final_high_water == initial_high_water + 2
    assert account_view["balanceWon"] == 100_000
    assert {event["data"]["reason"] for event in rejections} >= {
        "insufficient_funds",
        "same_account_transfer",
    }


def _concurrent_withdrawal(database_url: str, account_id: str, key: str, barrier: Barrier) -> int:
    database = Database(database_url)
    try:
        barrier.wait(timeout=5)
        result = Ledger(database, PARTNER_ID).withdraw(account_id, 75_000, key)
        return result.status_code
    finally:
        database.dispose()


def test_concurrent_debits_do_not_overdraw_or_lose_rejection_event(database_url: str) -> None:
    with make_client(database_url) as client:
        account = seed_accounts(client, f"ledger-concurrency-{uuid4()}")[0]["accountId"]

    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        request_id = str(uuid4())
        statuses = list(
            executor.map(
                lambda key: _concurrent_withdrawal(database_url, account, key, barrier),
                [f"concurrent-withdrawal-a-{request_id}", f"concurrent-withdrawal-b-{request_id}"],
            )
        )

    with make_client(database_url) as client:
        account_view = client.get(f"/v1/accounts/{account}", headers=auth_headers()).json()
        events = client.get(
            "/v1/events", params={"entityId": account}, headers=auth_headers()
        ).json()["items"]

    assert sorted(statuses) == [200, 409]
    assert account_view["balanceWon"] == 25_000
    assert sum(event["eventType"] == "withdrawal.completed" for event in events) == 1
    assert sum(event["eventType"] == "transaction.rejected" for event in events) == 1
