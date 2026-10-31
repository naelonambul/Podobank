"""MariaDB transaction boundary and SQLAlchemy Core repositories."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import Engine


def _to_database_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC).replace(tzinfo=None)


def _from_database_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True)
class Event:
    event_id: str
    schema_version: int
    event_type: str
    occurred_at: datetime
    recorded_at: datetime
    correlation_id: str
    entity_refs: dict[str, str]
    data: dict[str, Any]
    sequence: int | None = None


@dataclass(frozen=True)
class Account:
    account_id: str
    customer_id: str
    balance_won: int
    currency: str
    created_at: datetime


class CustomerRepository:
    def create(
        self,
        connection: Connection,
        customer_id: str,
        profile: Mapping[str, Any],
        created_at: datetime,
    ) -> None:
        connection.execute(
            text(
                "INSERT INTO customers (customer_id, profile_json, created_at) "
                "VALUES (:customer_id, :profile_json, :created_at)"
            ),
            {
                "customer_id": customer_id,
                "profile_json": json.dumps(profile, separators=(",", ":"), sort_keys=True),
                "created_at": _to_database_time(created_at),
            },
        )


class AccountRepository:
    def create(
        self,
        connection: Connection,
        account_id: str,
        customer_id: str,
        balance_won: int,
        created_at: datetime,
    ) -> Account:
        if balance_won < 0:
            raise ValueError("balance_won must be non-negative")
        connection.execute(
            text(
                "INSERT INTO accounts "
                "(account_id, customer_id, balance_won, currency, created_at) "
                "VALUES (:account_id, :customer_id, :balance_won, 'KRW', :created_at)"
            ),
            {
                "account_id": account_id,
                "customer_id": customer_id,
                "balance_won": balance_won,
                "created_at": _to_database_time(created_at),
            },
        )
        return Account(account_id, customer_id, balance_won, "KRW", created_at)

    def get(self, connection: Connection, account_id: str) -> Account | None:
        row = (
            connection.execute(
                text(
                    "SELECT account_id, customer_id, balance_won, currency, created_at "
                    "FROM accounts WHERE account_id = :account_id"
                ),
                {"account_id": account_id},
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return Account(
            account_id=str(row["account_id"]),
            customer_id=str(row["customer_id"]),
            balance_won=int(row["balance_won"]),
            currency=str(row["currency"]),
            created_at=_from_database_time(row["created_at"]),
        )

    def set_balance(self, connection: Connection, account_id: str, balance_won: int) -> None:
        if balance_won < 0:
            raise ValueError("balance_won must be non-negative")
        result = connection.execute(
            text("UPDATE accounts SET balance_won = :balance_won WHERE account_id = :account_id"),
            {"account_id": account_id, "balance_won": balance_won},
        )
        if result.rowcount != 1:
            raise LookupError(f"account {account_id} does not exist")


class EventRepository:
    def append(self, connection: Connection, event: Event) -> Event:
        connection.execute(
            text(
                "UPDATE event_sequence_state "
                "SET last_sequence = last_sequence + 1 WHERE singleton_id = 1"
            )
        )
        sequence = int(
            connection.execute(
                text("SELECT last_sequence FROM event_sequence_state WHERE singleton_id = 1")
            ).scalar_one()
        )
        result = connection.execute(
            text(
                "INSERT INTO domain_events "
                "(sequence, event_id, schema_version, event_type, occurred_at, recorded_at, "
                "correlation_id, entity_refs, data) VALUES "
                "(:sequence, :event_id, :schema_version, :event_type, :occurred_at, :recorded_at, "
                ":correlation_id, :entity_refs, :data)"
            ),
            {
                "sequence": sequence,
                "event_id": event.event_id,
                "schema_version": event.schema_version,
                "event_type": event.event_type,
                "occurred_at": _to_database_time(event.occurred_at),
                "recorded_at": _to_database_time(event.recorded_at),
                "correlation_id": event.correlation_id,
                "entity_refs": json.dumps(event.entity_refs, separators=(",", ":"), sort_keys=True),
                "data": json.dumps(event.data, separators=(",", ":"), sort_keys=True),
            },
        )
        connection.execute(
            text(
                "INSERT INTO telemetry_outbox (event_id, created_at) "
                "VALUES (:event_id, :created_at)"
            ),
            {"event_id": event.event_id, "created_at": _to_database_time(event.recorded_at)},
        )
        if result.rowcount != 1:
            raise RuntimeError("event sequence insert did not write one event")
        return replace(event, sequence=sequence)

    def high_water(self, connection: Connection) -> int:
        return int(
            connection.execute(
                text("SELECT last_sequence FROM event_sequence_state WHERE singleton_id = 1")
            ).scalar_one()
        )

    def list_after(
        self,
        connection: Connection,
        *,
        after_sequence: int,
        high_water_sequence: int,
        limit: int,
        event_type: str | None = None,
        entity_id: str | None = None,
        correlation_id: str | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
    ) -> list[Event]:
        if after_sequence < 0 or high_water_sequence < after_sequence:
            raise ValueError("event cursor sequence bounds are invalid")
        if limit < 1:
            raise ValueError("limit must be positive")
        rows = connection.execute(
            text(
                "SELECT sequence, event_id, schema_version, event_type, occurred_at, recorded_at, "
                "correlation_id, entity_refs, data FROM domain_events "
                "WHERE sequence > :after_sequence AND sequence <= :high_water_sequence "
                "AND (:event_type IS NULL OR event_type = :event_type) "
                "AND (:entity_id IS NULL OR "
                "JSON_SEARCH(entity_refs, 'one', :entity_id) IS NOT NULL) "
                "AND (:correlation_id IS NULL OR correlation_id = :correlation_id) "
                "AND (:occurred_from IS NULL OR occurred_at >= :occurred_from) "
                "AND (:occurred_to IS NULL OR occurred_at < :occurred_to) "
                "ORDER BY sequence ASC LIMIT :limit"
            ),
            {
                "after_sequence": after_sequence,
                "high_water_sequence": high_water_sequence,
                "limit": limit,
                "event_type": event_type,
                "entity_id": entity_id,
                "correlation_id": correlation_id,
                "occurred_from": (
                    _to_database_time(occurred_from) if occurred_from is not None else None
                ),
                "occurred_to": _to_database_time(occurred_to) if occurred_to is not None else None,
            },
        ).mappings()
        events: list[Event] = []
        for row in rows:
            entity_refs = row["entity_refs"]
            data = row["data"]
            events.append(
                Event(
                    event_id=str(row["event_id"]),
                    schema_version=int(row["schema_version"]),
                    event_type=str(row["event_type"]),
                    occurred_at=_from_database_time(row["occurred_at"]),
                    recorded_at=_from_database_time(row["recorded_at"]),
                    correlation_id=str(row["correlation_id"]),
                    entity_refs=json.loads(entity_refs)
                    if isinstance(entity_refs, str)
                    else entity_refs,
                    data=json.loads(data) if isinstance(data, str) else data,
                    sequence=int(row["sequence"]),
                )
            )
        return events


class CatalogSnapshotRepository:
    def save(
        self,
        connection: Connection,
        *,
        snapshot_id: str,
        product_ref: str,
        institution_name: str,
        product_name: str,
        product_category: str,
        facts: Mapping[str, Any],
        source_url: str,
        retrieved_at: datetime,
        effective_date: date | None,
        source_status: str,
    ) -> None:
        connection.execute(
            text(
                "INSERT INTO loan_product_snapshots "
                "(snapshot_id, product_ref, institution_name, product_name, product_category, "
                "facts_json, source_url, retrieved_at, effective_date, source_status, created_at) "
                "VALUES (:snapshot_id, :product_ref, :institution_name, :product_name, "
                ":product_category, :facts_json, :source_url, :retrieved_at, :effective_date, "
                ":source_status, :created_at)"
            ),
            {
                "snapshot_id": snapshot_id,
                "product_ref": product_ref,
                "institution_name": institution_name,
                "product_name": product_name,
                "product_category": product_category,
                "facts_json": json.dumps(facts, separators=(",", ":"), sort_keys=True),
                "source_url": source_url,
                "retrieved_at": _to_database_time(retrieved_at),
                "effective_date": effective_date,
                "source_status": source_status,
                "created_at": _to_database_time(retrieved_at),
            },
        )


class IdempotencyRepository:
    def get(self, connection: Connection, partner_id: str, key: str) -> Mapping[str, Any] | None:
        row = (
            connection.execute(
                text(
                    "SELECT request_hash, response_json FROM idempotency_records "
                    "WHERE partner_id = :partner_id AND idempotency_key = :idempotency_key"
                ),
                {"partner_id": partner_id, "idempotency_key": key},
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def insert(
        self,
        connection: Connection,
        *,
        partner_id: str,
        key: str,
        request_hash: str,
        response: Mapping[str, Any] | None,
        created_at: datetime,
    ) -> None:
        connection.execute(
            text(
                "INSERT INTO idempotency_records "
                "(partner_id, idempotency_key, request_hash, response_json, created_at) "
                "VALUES (:partner_id, :idempotency_key, :request_hash, :response_json, :created_at)"
            ),
            {
                "partner_id": partner_id,
                "idempotency_key": key,
                "request_hash": request_hash,
                "response_json": (
                    json.dumps(response, separators=(",", ":"), sort_keys=True)
                    if response is not None
                    else None
                ),
                "created_at": _to_database_time(created_at),
            },
        )


class Database:
    def __init__(self, url: str) -> None:
        self.engine: Engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args={"charset": "utf8mb4"},
        )
        self.customers = CustomerRepository()
        self.accounts = AccountRepository()
        self.events = EventRepository()
        self.catalog_snapshots = CatalogSnapshotRepository()
        self.idempotency = IdempotencyRepository()

    def initialize_schema(self) -> None:
        schema_path = Path(__file__).with_name("schema.sql")
        statements = [part.strip() for part in schema_path.read_text(encoding="utf-8").split(";")]
        with self.engine.begin() as connection:
            for statement in statements:
                if statement:
                    connection.exec_driver_sql(statement)
            connection.execute(
                text(
                    "INSERT IGNORE INTO event_sequence_state (singleton_id, last_sequence) "
                    "VALUES (1, 0)"
                )
            )
            connection.execute(
                text(
                    "UPDATE event_sequence_state SET last_sequence = GREATEST(last_sequence, "
                    "(SELECT COALESCE(MAX(sequence), 0) FROM domain_events)) "
                    "WHERE singleton_id = 1"
                )
            )

    def transaction(self) -> Any:
        return self.engine.begin()

    def dispose(self) -> None:
        self.engine.dispose()
