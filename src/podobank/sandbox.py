"""Reusable synthetic sandbox seed data."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import text

from podobank.db import Database
from podobank.events import append_event


def seed_sandbox(
    database: Database,
    *,
    partner_id: str,
    sandbox_id: str,
    customer_count: int,
    merchant_count: int,
) -> dict[str, Any]:
    namespace = uuid5(NAMESPACE_URL, f"podobank:{partner_id}:{sandbox_id}")
    correlation_id = str(uuid5(namespace, "seed-correlation"))
    customers: list[dict[str, str]] = []
    merchants: list[dict[str, str]] = []
    event_ids: list[str] = []
    now = datetime.now(UTC)

    with database.transaction() as connection:
        for index in range(customer_count):
            customer_id = str(uuid5(namespace, f"customer:{index}"))
            account_id = str(uuid5(namespace, f"account:{index}"))
            customer_exists = connection.execute(
                text("SELECT customer_id FROM customers WHERE customer_id = :customer_id"),
                {"customer_id": customer_id},
            ).scalar_one_or_none()
            if customer_exists is None:
                profile = {
                    "simulation": True,
                    "incomeBand": ["low", "middle", "high"][index % 3],
                    "employmentCategory": ["employee", "self_employed", "student"][index % 3],
                    "creditScoreBand": ["fair", "good", "very_good"][index % 3],
                }
                database.customers.create(connection, customer_id, profile, now)
                database.accounts.create(
                    connection,
                    account_id=account_id,
                    customer_id=customer_id,
                    balance_won=100_000 + index * 25_000,
                    created_at=now,
                )
                append_event(
                    database,
                    event_type="customer.created",
                    entity_refs={"customerId": customer_id},
                    correlation_id=correlation_id,
                    data={"simulation": True, "profile": profile},
                    connection=connection,
                    occurred_at=now,
                    event_id=str(uuid5(namespace, f"customer-created:{index}")),
                )
                append_event(
                    database,
                    event_type="account.opened",
                    entity_refs={"customerId": customer_id, "accountId": account_id},
                    correlation_id=correlation_id,
                    data={"simulation": True, "currency": "KRW"},
                    connection=connection,
                    occurred_at=now,
                    event_id=str(uuid5(namespace, f"account-opened:{index}")),
                )
            customers.append({"customerId": customer_id, "accountId": account_id})
            event_ids.extend(
                [
                    str(uuid5(namespace, f"customer-created:{index}")),
                    str(uuid5(namespace, f"account-opened:{index}")),
                ]
            )

        for index in range(merchant_count):
            merchant_id = str(uuid5(namespace, f"merchant:{index}"))
            display_name = f"Sandbox Merchant {index + 1}"
            merchant_exists = connection.execute(
                text("SELECT merchant_id FROM merchants WHERE merchant_id = :merchant_id"),
                {"merchant_id": merchant_id},
            ).scalar_one_or_none()
            if merchant_exists is None:
                connection.execute(
                    text(
                        "INSERT INTO merchants (merchant_id, partner_id, display_name, created_at) "
                        "VALUES (:merchant_id, :partner_id, :display_name, :created_at)"
                    ),
                    {
                        "merchant_id": merchant_id,
                        "partner_id": partner_id,
                        "display_name": display_name,
                        "created_at": now.replace(tzinfo=None),
                    },
                )
                append_event(
                    database,
                    event_type="merchant.created",
                    entity_refs={"merchantId": merchant_id},
                    correlation_id=correlation_id,
                    data={"simulation": True, "displayName": display_name},
                    connection=connection,
                    occurred_at=now,
                    event_id=str(uuid5(namespace, f"merchant-created:{index}")),
                )
            merchants.append({"merchantId": merchant_id, "displayName": display_name})
            event_ids.append(str(uuid5(namespace, f"merchant-created:{index}")))

    return {
        "sandboxId": sandbox_id,
        "correlationId": correlation_id,
        "customers": customers,
        "merchants": merchants,
        "eventIds": event_ids,
        "simulation": True,
    }
