"""Atomic synthetic deposits, withdrawals, and internal transfers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from podobank.db import Account, Database
from podobank.events import append_event

MAX_TRANSACTION_AMOUNT_WON = (1 << 64) - 1


class AccountNotFound(LookupError):
    """Raised when a requested synthetic account does not exist."""


class IdempotencyConflict(ValueError):
    """Raised when an idempotency key is reused with a different request."""


@dataclass(frozen=True)
class OperationResult:
    status_code: int
    body: dict[str, Any]
    error_code: str | None = None
    error_message: str | None = None

    def to_storage(self) -> dict[str, Any]:
        return {
            "statusCode": self.status_code,
            "body": self.body,
            "errorCode": self.error_code,
            "errorMessage": self.error_message,
        }

    @classmethod
    def from_storage(cls, value: Mapping[str, Any]) -> OperationResult:
        body = value.get("body")
        if not isinstance(body, dict):
            raise RuntimeError("stored idempotency result has an invalid body")
        status_code = value.get("statusCode")
        if not isinstance(status_code, int):
            raise RuntimeError("stored idempotency result has an invalid status")
        error_code = value.get("errorCode")
        error_message = value.get("errorMessage")
        return cls(
            status_code=status_code,
            body=body,
            error_code=error_code if isinstance(error_code, str) else None,
            error_message=error_message if isinstance(error_message, str) else None,
        )


_Mutation = Callable[[Connection, dict[str, Account], str, datetime], OperationResult]


class Ledger:
    def __init__(self, database: Database, partner_id: str) -> None:
        self.database = database
        self.partner_id = partner_id

    def deposit(
        self,
        account_id: str,
        amount_won: int,
        key: str,
        *,
        correlation_id: str | None = None,
        event_context: Mapping[str, Any] | None = None,
    ) -> OperationResult:
        self._validate_amount(amount_won)

        def apply(
            connection: Connection,
            accounts: dict[str, Account],
            operation_correlation_id: str,
            now: datetime,
        ) -> OperationResult:
            account = accounts[account_id]
            new_balance = account.balance_won + amount_won
            if new_balance > MAX_TRANSACTION_AMOUNT_WON:
                return self._record_rejection(
                    connection,
                    operation_type="deposit",
                    amount_won=amount_won,
                    accounts=accounts,
                    reason="balance_limit_exceeded",
                    correlation_id=operation_correlation_id,
                    now=now,
                    event_context=event_context,
                    error_message="The account balance would exceed the supported range.",
                )
            self.database.accounts.set_balance(connection, account_id, new_balance)
            return self._record_success(
                connection,
                operation_type="deposit",
                event_type="deposit.completed",
                amount_won=amount_won,
                accounts=accounts,
                resulting_balances={account_id: new_balance},
                correlation_id=operation_correlation_id,
                now=now,
                event_context=event_context,
            )

        return self._operate(
            operation_type="deposit",
            request={"accountId": account_id, "amountWon": amount_won},
            account_ids=[account_id],
            key=key,
            correlation_id=correlation_id,
            mutation=apply,
        )

    def withdraw(
        self,
        account_id: str,
        amount_won: int,
        key: str,
        *,
        correlation_id: str | None = None,
        event_context: Mapping[str, Any] | None = None,
    ) -> OperationResult:
        self._validate_amount(amount_won)

        def apply(
            connection: Connection,
            accounts: dict[str, Account],
            operation_correlation_id: str,
            now: datetime,
        ) -> OperationResult:
            account = accounts[account_id]
            if account.balance_won < amount_won:
                return self._record_rejection(
                    connection,
                    operation_type="withdrawal",
                    amount_won=amount_won,
                    accounts=accounts,
                    reason="insufficient_funds",
                    correlation_id=operation_correlation_id,
                    now=now,
                    event_context=event_context,
                    error_message="The account has insufficient funds.",
                )
            new_balance = account.balance_won - amount_won
            self.database.accounts.set_balance(connection, account_id, new_balance)
            return self._record_success(
                connection,
                operation_type="withdrawal",
                event_type="withdrawal.completed",
                amount_won=amount_won,
                accounts=accounts,
                resulting_balances={account_id: new_balance},
                correlation_id=operation_correlation_id,
                now=now,
                event_context=event_context,
            )

        return self._operate(
            operation_type="withdrawal",
            request={"accountId": account_id, "amountWon": amount_won},
            account_ids=[account_id],
            key=key,
            correlation_id=correlation_id,
            mutation=apply,
        )

    def transfer(
        self,
        source_account_id: str,
        destination_account_id: str,
        amount_won: int,
        key: str,
        *,
        correlation_id: str | None = None,
        event_context: Mapping[str, Any] | None = None,
    ) -> OperationResult:
        self._validate_amount(amount_won)

        def apply(
            connection: Connection,
            accounts: dict[str, Account],
            operation_correlation_id: str,
            now: datetime,
        ) -> OperationResult:
            source = accounts[source_account_id]
            if source_account_id == destination_account_id:
                return self._record_rejection(
                    connection,
                    operation_type="transfer",
                    amount_won=amount_won,
                    accounts=accounts,
                    reason="same_account_transfer",
                    correlation_id=operation_correlation_id,
                    now=now,
                    event_context=event_context,
                    error_message="Source and destination accounts must be different.",
                )
            destination = accounts[destination_account_id]
            if source.balance_won < amount_won:
                return self._record_rejection(
                    connection,
                    operation_type="transfer",
                    amount_won=amount_won,
                    accounts=accounts,
                    reason="insufficient_funds",
                    correlation_id=operation_correlation_id,
                    now=now,
                    event_context=event_context,
                    error_message="The source account has insufficient funds.",
                )
            destination_balance = destination.balance_won + amount_won
            if destination_balance > MAX_TRANSACTION_AMOUNT_WON:
                return self._record_rejection(
                    connection,
                    operation_type="transfer",
                    amount_won=amount_won,
                    accounts=accounts,
                    reason="balance_limit_exceeded",
                    correlation_id=operation_correlation_id,
                    now=now,
                    event_context=event_context,
                    error_message="The destination balance would exceed the supported range.",
                )
            source_balance = source.balance_won - amount_won
            self.database.accounts.set_balance(connection, source_account_id, source_balance)
            self.database.accounts.set_balance(
                connection, destination_account_id, destination_balance
            )
            return self._record_success(
                connection,
                operation_type="transfer",
                event_type="transfer.completed",
                amount_won=amount_won,
                accounts=accounts,
                resulting_balances={
                    source_account_id: source_balance,
                    destination_account_id: destination_balance,
                },
                correlation_id=operation_correlation_id,
                now=now,
                event_context=event_context,
            )

        return self._operate(
            operation_type="transfer",
            request={
                "sourceAccountId": source_account_id,
                "destinationAccountId": destination_account_id,
                "amountWon": amount_won,
            },
            account_ids=[source_account_id, destination_account_id],
            key=key,
            correlation_id=correlation_id,
            mutation=apply,
        )

    def _operate(
        self,
        *,
        operation_type: str,
        request: Mapping[str, Any],
        account_ids: list[str],
        key: str,
        correlation_id: str | None,
        mutation: _Mutation,
    ) -> OperationResult:
        if not key or len(key) > 128:
            raise ValueError("Idempotency-Key must contain between 1 and 128 characters.")
        now = datetime.now(UTC)
        request_hash = hashlib.sha256(
            json.dumps(
                {"operationType": operation_type, **request},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        operation_correlation_id = correlation_id or str(uuid4())

        with self.database.transaction() as connection:
            created = self.database.idempotency.reserve(
                connection,
                partner_id=self.partner_id,
                key=key,
                request_hash=request_hash,
                created_at=now,
            )
            if not created:
                existing = self.database.idempotency.get(connection, self.partner_id, key)
                if existing is None:
                    raise RuntimeError("idempotency reservation disappeared")
                if existing["request_hash"] != request_hash:
                    raise IdempotencyConflict(
                        "Idempotency-Key was already used with a different request."
                    )
                stored = existing["response_json"]
                if isinstance(stored, str):
                    stored = json.loads(stored)
                if not isinstance(stored, Mapping):
                    raise RuntimeError("idempotency result was not committed with its reservation")
                return OperationResult.from_storage(stored)

            locked_accounts: dict[str, Account] = {}
            for account_id in sorted(set(account_ids)):
                account = self.database.accounts.get_for_update(connection, account_id)
                if account is None:
                    raise AccountNotFound(f"Account {account_id} does not exist.")
                locked_accounts[account_id] = account
            accounts = {
                account_id: locked_accounts[account_id] for account_id in dict.fromkeys(account_ids)
            }

            result = mutation(connection, accounts, operation_correlation_id, now)
            self.database.idempotency.complete(
                connection,
                partner_id=self.partner_id,
                key=key,
                response=result.to_storage(),
            )
            return result

    def _record_success(
        self,
        connection: Connection,
        *,
        operation_type: str,
        event_type: str,
        amount_won: int,
        accounts: Mapping[str, Account],
        resulting_balances: Mapping[str, int],
        correlation_id: str,
        now: datetime,
        event_context: Mapping[str, Any] | None,
    ) -> OperationResult:
        return self._record(
            connection,
            operation_type=operation_type,
            event_type=event_type,
            amount_won=amount_won,
            accounts=accounts,
            resulting_balances=resulting_balances,
            correlation_id=correlation_id,
            now=now,
            event_context=event_context,
            reason=None,
            error_code=None,
            error_message=None,
        )

    def _record_rejection(
        self,
        connection: Connection,
        *,
        operation_type: str,
        amount_won: int,
        accounts: Mapping[str, Account],
        reason: str,
        correlation_id: str,
        now: datetime,
        event_context: Mapping[str, Any] | None,
        error_message: str,
    ) -> OperationResult:
        return self._record(
            connection,
            operation_type=operation_type,
            event_type="transaction.rejected",
            amount_won=amount_won,
            accounts=accounts,
            resulting_balances={
                account_id: account.balance_won for account_id, account in accounts.items()
            },
            correlation_id=correlation_id,
            now=now,
            event_context=event_context,
            reason=reason,
            error_code=reason,
            error_message=error_message,
        )

    def _record(
        self,
        connection: Connection,
        *,
        operation_type: str,
        event_type: str,
        amount_won: int,
        accounts: Mapping[str, Account],
        resulting_balances: Mapping[str, int],
        correlation_id: str,
        now: datetime,
        event_context: Mapping[str, Any] | None,
        reason: str | None,
        error_code: str | None,
        error_message: str | None,
    ) -> OperationResult:
        operation_id = str(uuid4())
        entity_refs: dict[str, str] = {}
        if operation_type == "transfer":
            source_id = next(iter(accounts))
            destination_id = next(
                (account_id for account_id in accounts if account_id != source_id), source_id
            )
            entity_refs = {
                "sourceAccountId": source_id,
                "destinationAccountId": destination_id,
                "sourceCustomerId": accounts[source_id].customer_id,
                "destinationCustomerId": accounts[destination_id].customer_id,
            }
        else:
            account_id = next(iter(accounts))
            entity_refs = {
                "accountId": account_id,
                "customerId": accounts[account_id].customer_id,
            }

        event_id = str(uuid4())
        data: dict[str, Any] = {
            "operationId": operation_id,
            "operationType": operation_type,
            "amountWon": amount_won,
            "currency": "KRW",
            "simulation": True,
            **(dict(event_context) if event_context is not None else {}),
        }
        if reason is not None:
            data["reason"] = reason
        if operation_type == "transfer":
            source_id = next(iter(accounts))
            destination_id = next(
                (account_id for account_id in accounts if account_id != source_id), source_id
            )
            data["sourceBalanceWon"] = resulting_balances[source_id]
            data["destinationBalanceWon"] = resulting_balances[destination_id]
        else:
            account_id = next(iter(accounts))
            data["balanceWon"] = resulting_balances[account_id]
        append_event(
            self.database,
            event_type=event_type,
            entity_refs=entity_refs,
            correlation_id=correlation_id,
            data=data,
            connection=connection,
            occurred_at=now,
            event_id=event_id,
        )

        body: dict[str, Any] = {
            "operationId": operation_id,
            "operationType": operation_type,
            "status": "rejected" if reason is not None else "completed",
            "amountWon": amount_won,
            "currency": "KRW",
            "correlationId": correlation_id,
            "eventIds": [event_id],
            "simulation": True,
        }
        if operation_type == "transfer":
            source_id = next(iter(accounts))
            destination_id = next(
                (account_id for account_id in accounts if account_id != source_id), source_id
            )
            body.update(
                {
                    "sourceAccountId": source_id,
                    "destinationAccountId": destination_id,
                    "sourceBalanceWon": resulting_balances[source_id],
                    "destinationBalanceWon": resulting_balances[destination_id],
                }
            )
        else:
            account_id = next(iter(accounts))
            body.update(
                {
                    "accountId": account_id,
                    "balanceWon": resulting_balances[account_id],
                }
            )
        if reason is not None:
            body["reason"] = reason
        return OperationResult(
            status_code=409 if reason is not None else 200,
            body=body,
            error_code=error_code,
            error_message=error_message,
        )

    @staticmethod
    def _validate_amount(amount_won: int) -> None:
        if isinstance(amount_won, bool) or not isinstance(amount_won, int):
            raise ValueError("amount_won must be an integer number of won.")
        if amount_won < 1 or amount_won > MAX_TRANSACTION_AMOUNT_WON:
            raise ValueError("amount_won is outside the supported positive range.")
