"""Idempotent synthetic loan applications and account disbursements."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Connection, text

from podobank.db import Database
from podobank.events import append_event
from podobank.ledger import MAX_TRANSACTION_AMOUNT_WON, IdempotencyConflict

MAX_LOAN_TERM_MONTHS = 600


class LoanResourceNotFound(LookupError):
    """Raised when a synthetic account, customer, or product snapshot is missing."""


def reserve_idempotent_request(
    database: Database,
    connection: Connection,
    *,
    partner_id: str,
    idempotency_key: str,
    operation_type: str,
    request: Mapping[str, Any],
    created_at: datetime,
) -> dict[str, Any] | None:
    if not idempotency_key or len(idempotency_key) > 128:
        raise ValueError("Idempotency-Key must contain between 1 and 128 characters.")
    request_hash = hashlib.sha256(
        json.dumps(
            {"operationType": operation_type, **request},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    created = database.idempotency.reserve(
        connection,
        partner_id=partner_id,
        key=idempotency_key,
        request_hash=request_hash,
        created_at=created_at,
    )
    if created:
        return None
    existing = database.idempotency.get(connection, partner_id, idempotency_key)
    if existing is None:
        raise RuntimeError("idempotency reservation disappeared")
    if existing["request_hash"] != request_hash:
        raise IdempotencyConflict("Idempotency-Key was already used with a different request.")
    response = existing["response_json"]
    if isinstance(response, str):
        response = json.loads(response)
    if not isinstance(response, Mapping):
        raise RuntimeError("idempotency result was not committed with its reservation")
    return dict(response)


def complete_idempotent_request(
    database: Database,
    connection: Connection,
    *,
    partner_id: str,
    idempotency_key: str,
    response: Mapping[str, Any],
) -> None:
    database.idempotency.complete(
        connection,
        partner_id=partner_id,
        key=idempotency_key,
        response=response,
    )


def create_simulated_loan(
    database: Database,
    *,
    partner_id: str,
    customer_id: str,
    account_id: str,
    snapshot_id: str,
    amount_won: int,
    term_months: int,
    scenario_seed: int,
    idempotency_key: str,
) -> dict[str, Any]:
    if (
        isinstance(amount_won, bool)
        or not isinstance(amount_won, int)
        or not 1 <= amount_won <= MAX_TRANSACTION_AMOUNT_WON
    ):
        raise ValueError("amount_won is outside the supported positive range.")
    if isinstance(term_months, bool) or not isinstance(term_months, int):
        raise ValueError("term_months must be an integer number of months.")
    if not 1 <= term_months <= MAX_LOAN_TERM_MONTHS:
        raise ValueError("term_months is outside the supported range.")
    if isinstance(scenario_seed, bool) or not isinstance(scenario_seed, int):
        raise ValueError("scenario_seed must be a non-negative integer.")
    if not 0 <= scenario_seed <= (1 << 63) - 1:
        raise ValueError("scenario_seed is outside the supported range.")
    now = datetime.now(UTC)
    request_data = {
        "customerId": customer_id,
        "accountId": account_id,
        "snapshotId": snapshot_id,
        "amountWon": amount_won,
        "termMonths": term_months,
        "scenarioSeed": scenario_seed,
    }
    with database.transaction() as connection:
        replay = reserve_idempotent_request(
            database,
            connection,
            partner_id=partner_id,
            idempotency_key=idempotency_key,
            operation_type="loan.application",
            request=request_data,
            created_at=now,
        )
        if replay is not None:
            return replay

        database.catalog_snapshots.acquire_writer_lock(connection)
        account = database.accounts.get_for_update(connection, account_id)
        if account is None or account.customer_id != customer_id:
            raise LoanResourceNotFound("The synthetic customer or account was not found.")
        snapshot = database.catalog_snapshots.get_by_id(connection, snapshot_id)
        if snapshot is None:
            raise LoanResourceNotFound("The loan-product snapshot was not found.")

        latest_snapshot = database.catalog_snapshots.get_latest_for_product(
            connection, str(snapshot["product_ref"])
        )
        reason: str | None
        if (
            latest_snapshot is None
            or latest_snapshot["snapshot_id"] != snapshot_id
            or latest_snapshot["source_status"] != "active"
        ):
            reason = "product_snapshot_not_current"
        else:
            reason = _application_rejection(
                snapshot,
                amount_won=amount_won,
                term_months=term_months,
                scenario_seed=scenario_seed,
                balance_won=account.balance_won,
            )
        loan_id = str(uuid4())
        correlation_id = str(uuid4())
        status = "rejected" if reason is not None else "disbursed"
        connection.execute(
            text(
                "INSERT INTO loans (loan_id, customer_id, account_id, snapshot_id, amount_won, "
                "term_months, status, created_at, updated_at) VALUES "
                "(:loan_id, :customer_id, :account_id, :snapshot_id, :amount_won, "
                ":term_months, :status, :created_at, :updated_at)"
            ),
            {
                "loan_id": loan_id,
                "customer_id": customer_id,
                "account_id": account_id,
                "snapshot_id": snapshot_id,
                "amount_won": amount_won,
                "term_months": term_months,
                "status": status,
                "created_at": _to_database_time(now),
                "updated_at": _to_database_time(now),
            },
        )

        event_ids: list[str] = []
        common_data: dict[str, Any] = {
            "loanId": loan_id,
            "productRef": snapshot["product_ref"],
            "snapshotId": snapshot_id,
            "amountWon": amount_won,
            "termMonths": term_months,
            "scenarioSeed": scenario_seed,
            "simulation": True,
        }
        application_event = append_event(
            database,
            event_type="loan.application.created",
            entity_refs={
                "loanId": loan_id,
                "customerId": customer_id,
                "accountId": account_id,
                "snapshotId": snapshot_id,
            },
            correlation_id=correlation_id,
            data=common_data,
            connection=connection,
            occurred_at=now,
        )
        event_ids.append(application_event.event_id)

        if reason is not None:
            rejected_event = append_event(
                database,
                event_type="loan.application.rejected",
                entity_refs={
                    "loanId": loan_id,
                    "customerId": customer_id,
                    "accountId": account_id,
                    "snapshotId": snapshot_id,
                },
                correlation_id=correlation_id,
                data={**common_data, "reason": reason},
                connection=connection,
                occurred_at=now,
            )
            event_ids.append(rejected_event.event_id)
        else:
            new_balance = account.balance_won + amount_won
            database.accounts.set_balance(connection, account_id, new_balance)
            account_event = append_event(
                database,
                event_type="account.credited",
                entity_refs={
                    "loanId": loan_id,
                    "customerId": customer_id,
                    "accountId": account_id,
                },
                correlation_id=correlation_id,
                data={
                    "amountWon": amount_won,
                    "balanceWon": new_balance,
                    "currency": "KRW",
                    "reason": "simulated_loan_disbursement",
                    "simulation": True,
                },
                connection=connection,
                occurred_at=now,
            )
            disbursement_event = append_event(
                database,
                event_type="loan.disbursement.completed",
                entity_refs={
                    "loanId": loan_id,
                    "customerId": customer_id,
                    "accountId": account_id,
                    "snapshotId": snapshot_id,
                },
                correlation_id=correlation_id,
                data={**common_data, "balanceWon": new_balance},
                connection=connection,
                occurred_at=now,
            )
            event_ids.extend([account_event.event_id, disbursement_event.event_id])

        response: dict[str, Any] = {
            "loanId": loan_id,
            "customerId": customer_id,
            "accountId": account_id,
            "productRef": snapshot["product_ref"],
            "snapshotId": snapshot_id,
            "amountWon": amount_won,
            "termMonths": term_months,
            "scenarioSeed": scenario_seed,
            "status": status,
            "correlationId": correlation_id,
            "eventIds": event_ids,
            "simulation": True,
        }
        if reason is not None:
            response["reason"] = reason
        complete_idempotent_request(
            database,
            connection,
            partner_id=partner_id,
            idempotency_key=idempotency_key,
            response=response,
        )
        return response


def _application_rejection(
    snapshot: Mapping[str, Any],
    *,
    amount_won: int,
    term_months: int,
    scenario_seed: int,
    balance_won: int,
) -> str | None:
    if snapshot["source_status"] != "active":
        return "product_retired"
    facts = snapshot["facts"]
    minimum_amount = _known_integer(facts.get("amountMinimumWon"))
    maximum_amount = _known_integer(facts.get("amountMaximumWon"))
    if minimum_amount is not None and amount_won < minimum_amount:
        return "below_published_amount_minimum"
    if maximum_amount is not None and amount_won > maximum_amount:
        return "above_published_amount_maximum"
    minimum_term = _known_integer(facts.get("termMinimumMonths"))
    maximum_term = _known_integer(facts.get("termMaximumMonths"))
    if minimum_term is not None and term_months < minimum_term:
        return "below_published_term_minimum"
    if maximum_term is not None and term_months > maximum_term:
        return "above_published_term_maximum"
    if scenario_seed % 2 == 1:
        return "scenario_seed_rejected"
    if balance_won + amount_won > MAX_TRANSACTION_AMOUNT_WON:
        return "account_balance_limit_exceeded"
    return None


def _known_integer(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _to_database_time(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None)
