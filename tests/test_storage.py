from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError


def create_database(database_url: str) -> Any:
    try:
        module_spec = importlib.util.find_spec("podobank.db")
    except ModuleNotFoundError:
        module_spec = None
    assert module_spec is not None, "The MariaDB persistence module must be implemented."
    from podobank.db import Database

    database = Database(database_url)
    database.initialize_schema()
    return database


def make_event(event_id: str, event_type: str = "deposit.completed") -> Any:
    from podobank.db import Event

    now = datetime(2026, 1, 1, tzinfo=UTC)
    return Event(
        event_id=event_id,
        schema_version=1,
        event_type=event_type,
        occurred_at=now,
        recorded_at=now,
        correlation_id=str(uuid4()),
        entity_refs={"accountId": str(uuid4())},
        data={"amountWon": 100, "currency": "KRW"},
    )


def test_schema_initialization_creates_required_tables(database_url: str) -> None:
    database = create_database(database_url)
    try:
        tables = set(inspect(database.engine).get_table_names())
        assert {
            "customers",
            "accounts",
            "merchants",
            "loans",
            "payments",
            "idempotency_records",
            "loan_product_snapshots",
            "domain_events",
            "catalog_refresh_state",
            "telemetry_outbox",
        } <= tables
    finally:
        database.dispose()


def test_event_append_is_immutable_and_creates_one_outbox_row(database_url: str) -> None:
    database = create_database(database_url)
    event_id = str(uuid4())
    original = make_event(event_id)
    try:
        with database.transaction() as connection:
            stored = database.events.append(connection, original)

        with pytest.raises(IntegrityError):
            with database.transaction() as connection:
                database.events.append(connection, make_event(event_id, "withdrawal.completed"))

        with database.transaction() as connection:
            row = connection.execute(
                text("SELECT event_type FROM domain_events WHERE event_id = :event_id"),
                {"event_id": event_id},
            ).one()
            outbox_count = connection.execute(
                text("SELECT COUNT(*) FROM telemetry_outbox WHERE event_id = :event_id"),
                {"event_id": event_id},
            ).scalar_one()

        assert stored.sequence is not None
        assert row.event_type == "deposit.completed"
        assert outbox_count == 1
    finally:
        database.dispose()


def test_event_cursor_returns_sequence_order(database_url: str) -> None:
    database = create_database(database_url)
    event_ids = [str(uuid4()) for _ in range(3)]
    try:
        with database.transaction() as connection:
            first = database.events.append(connection, make_event(event_ids[0]))
        with database.transaction() as connection:
            second = database.events.append(connection, make_event(event_ids[1]))
        with database.transaction() as connection:
            third = database.events.append(connection, make_event(event_ids[2]))

        with database.transaction() as connection:
            first_page = database.events.list_after(
                connection,
                after_sequence=first.sequence - 1,
                high_water_sequence=third.sequence,
                limit=2,
            )
            second_page = database.events.list_after(
                connection,
                after_sequence=first_page[-1].sequence,
                high_water_sequence=third.sequence,
                limit=2,
            )

        assert [event.event_id for event in first_page] == event_ids[:2]
        assert [event.event_id for event in second_page] == event_ids[2:]
        assert first.sequence < second.sequence < third.sequence
    finally:
        database.dispose()


def test_balance_event_and_outbox_rollback_together(database_url: str) -> None:
    database = create_database(database_url)
    customer_id = str(uuid4())
    account_id = str(uuid4())
    event_id = str(uuid4())
    now = datetime(2026, 1, 1)
    try:
        with database.transaction() as connection:
            connection.execute(
                text(
                    "INSERT INTO customers (customer_id, profile_json, created_at) "
                    "VALUES (:customer_id, JSON_OBJECT(), :created_at)"
                ),
                {"customer_id": customer_id, "created_at": now},
            )
            connection.execute(
                text(
                    "INSERT INTO accounts "
                    "(account_id, customer_id, balance_won, currency, created_at) "
                    "VALUES (:account_id, :customer_id, 5000, 'KRW', :created_at)"
                ),
                {
                    "account_id": account_id,
                    "customer_id": customer_id,
                    "created_at": now,
                },
            )

        with pytest.raises(RuntimeError, match="force rollback"):
            with database.transaction() as connection:
                connection.execute(
                    text("UPDATE accounts SET balance_won = 4000 WHERE account_id = :account_id"),
                    {"account_id": account_id},
                )
                database.events.append(connection, make_event(event_id))
                raise RuntimeError("force rollback")

        with database.transaction() as connection:
            balance = connection.execute(
                text("SELECT balance_won FROM accounts WHERE account_id = :account_id"),
                {"account_id": account_id},
            ).scalar_one()
            event_count = connection.execute(
                text("SELECT COUNT(*) FROM domain_events WHERE event_id = :event_id"),
                {"event_id": event_id},
            ).scalar_one()
            outbox_count = connection.execute(
                text("SELECT COUNT(*) FROM telemetry_outbox WHERE event_id = :event_id"),
                {"event_id": event_id},
            ).scalar_one()

        assert balance == 5000
        assert event_count == 0
        assert outbox_count == 0
    finally:
        database.dispose()
