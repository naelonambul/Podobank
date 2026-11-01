import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeVar

from sqlalchemy.engine import Engine

from podobank_api.features.observability.events import record_financial_operation
from podobank_api.features.transactions import sql

logger = logging.getLogger(__name__)
MAX_BALANCE = 9_223_372_036_854_775_807
Result = TypeVar("Result")


class TransactionError(RuntimeError):
    reason = "transaction_rejected"


class InvalidAmountError(TransactionError):
    reason = "invalid_amount"


class AccountNotFoundError(TransactionError):
    reason = "account_not_found"


class RecipientNotFoundError(TransactionError):
    reason = "recipient_not_found"


class SelfTransferError(TransactionError):
    reason = "self_transfer"


class InsufficientFundsError(TransactionError):
    reason = "insufficient_funds"


@dataclass(frozen=True)
class TransactionResult:
    transaction_id: str
    account_id: int
    amount: int
    balance: int


def _validate_amount(amount: int) -> None:
    if isinstance(amount, bool) or not isinstance(amount, int) or not 1 <= amount <= MAX_BALANCE:
        raise InvalidAmountError("amount must be a positive whole KRW value")


def _posted_at() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class TransactionService:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def deposit(self, *, user_id: int, amount: int) -> TransactionResult:
        def perform() -> TransactionResult:
            _validate_amount(amount)
            transaction_id = str(uuid.uuid4())
            with self._engine.begin() as connection:
                account = sql.lock_account_by_owner(connection, user_id)
                if account is None:
                    raise AccountNotFoundError("customer account was not found")
                balance = int(account["balance"])
                if balance + amount > MAX_BALANCE:
                    raise InvalidAmountError("resulting balance exceeds the account limit")
                posted_at = _posted_at()
                sql.add_balance(connection, account_id=int(account["id"]), delta=amount)
                sql.insert_ledger_entry(
                    connection,
                    posted_at=posted_at,
                    transaction_id=transaction_id,
                    account_id=int(account["id"]),
                    user_id=user_id,
                    entry_type="deposit",
                    amount=amount,
                )
            return TransactionResult(transaction_id, int(account["id"]), amount, balance + amount)

        return self._run("deposit", perform)

    def withdraw(self, *, user_id: int, amount: int) -> TransactionResult:
        def perform() -> TransactionResult:
            _validate_amount(amount)
            transaction_id = str(uuid.uuid4())
            with self._engine.begin() as connection:
                account = sql.lock_account_by_owner(connection, user_id)
                if account is None:
                    raise AccountNotFoundError("customer account was not found")
                balance = int(account["balance"])
                if balance < amount:
                    raise InsufficientFundsError("account balance is insufficient")
                posted_at = _posted_at()
                sql.add_balance(connection, account_id=int(account["id"]), delta=-amount)
                sql.insert_ledger_entry(
                    connection,
                    posted_at=posted_at,
                    transaction_id=transaction_id,
                    account_id=int(account["id"]),
                    user_id=user_id,
                    entry_type="withdrawal",
                    amount=-amount,
                )
            return TransactionResult(transaction_id, int(account["id"]), amount, balance - amount)

        return self._run("withdrawal", perform)

    def transfer(
        self,
        *,
        user_id: int,
        destination_account_id: int,
        amount: int,
    ) -> TransactionResult:
        def perform() -> TransactionResult:
            _validate_amount(amount)
            transaction_id = str(uuid.uuid4())
            with self._engine.connect() as lookup_connection:
                source_id = sql.find_account_id_by_owner(lookup_connection, user_id)
            if source_id is None:
                raise AccountNotFoundError("customer account was not found")
            if source_id == destination_account_id:
                raise SelfTransferError("cannot transfer to the same account")

            with self._engine.begin() as connection:
                locked_accounts: dict[int, dict[str, object]] = {}
                for account_id in sorted((source_id, destination_account_id)):
                    account = sql.lock_account_by_id(connection, account_id)
                    if account is not None:
                        locked_accounts[account_id] = account

                source = locked_accounts.get(source_id)
                destination = locked_accounts.get(destination_account_id)
                if source is None:
                    raise AccountNotFoundError("customer account was not found")
                if destination is None:
                    raise RecipientNotFoundError("recipient account was not found")
                if int(source["owner_user_id"]) != user_id:
                    raise AccountNotFoundError("customer account was not found")
                destination_user_id = int(destination["owner_user_id"])
                if not sql.is_customer_user(connection, destination_user_id):
                    raise RecipientNotFoundError("recipient account was not found")

                balance = int(source["balance"])
                if balance < amount:
                    raise InsufficientFundsError("account balance is insufficient")
                if int(destination["balance"]) + amount > MAX_BALANCE:
                    raise InvalidAmountError("resulting balance exceeds the account limit")

                posted_at = _posted_at()
                sql.add_balance(connection, account_id=source_id, delta=-amount)
                sql.add_balance(connection, account_id=destination_account_id, delta=amount)
                sql.insert_ledger_entry(
                    connection,
                    posted_at=posted_at,
                    transaction_id=transaction_id,
                    account_id=source_id,
                    user_id=user_id,
                    entry_type="transfer_out",
                    amount=-amount,
                )
                sql.insert_ledger_entry(
                    connection,
                    posted_at=posted_at,
                    transaction_id=transaction_id,
                    account_id=destination_account_id,
                    user_id=destination_user_id,
                    entry_type="transfer_in",
                    amount=amount,
                )
            return TransactionResult(transaction_id, source_id, amount, balance - amount)

        return self._run("transfer", perform)

    @staticmethod
    def _run(operation: str, action: Callable[[], Result]) -> Result:
        try:
            result = action()
        except TransactionError as error:
            record_financial_operation(operation, "failure", error.reason)
            logger.info(
                "financial_operation operation=%s outcome=failure reason=%s",
                operation,
                error.reason,
            )
            raise
        except Exception:
            record_financial_operation(operation, "failure", "database_error")
            logger.info(
                "financial_operation operation=%s outcome=failure reason=database_error",
                operation,
            )
            raise
        record_financial_operation(operation, "success", "completed")
        logger.info(
            "financial_operation operation=%s outcome=success reason=completed",
            operation,
        )
        return result
