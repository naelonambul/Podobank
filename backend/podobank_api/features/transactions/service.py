from typing import Literal
from uuid import uuid4

from sqlalchemy.engine import Connection, Engine

from podobank_api.features.accounts.service import (
    account_by_number,
    account_by_user_id,
    credit_user_account,
    debit_user_account,
)
from podobank_api.features.transactions import sql


class TransactionError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _account_id(engine: Engine, user_id: int) -> int:
    with engine.connect() as connection:
        account = account_by_user_id(connection, user_id)
    if account is None:
        raise TransactionError(404, "account not found")
    return int(account["id"])


def deposit(engine: Engine, user_id: int, amount_krw: int, memo: str) -> dict[str, object]:
    transaction_id = str(uuid4())
    with engine.begin() as connection:
        account = account_by_user_id(connection, user_id)
        if account is None:
            raise TransactionError(404, "account not found")
        balance = credit_user_account(connection, user_id, amount_krw)
        sql.insert_entry(
            connection,
            transaction_id=transaction_id,
            account_id=int(account["id"]),
            entry_type="deposit",
            amount_krw=amount_krw,
            counterparty_account_number=None,
            memo=memo,
        )
    return {"transaction_id": transaction_id, "balance_krw": balance}


def withdraw(engine: Engine, user_id: int, amount_krw: int, memo: str) -> dict[str, object]:
    transaction_id = str(uuid4())
    with engine.begin() as connection:
        account = account_by_user_id(connection, user_id)
        if account is None:
            raise TransactionError(404, "account not found")
        balance = debit_user_account(connection, user_id, amount_krw)
        if balance is None:
            raise TransactionError(409, "insufficient funds")
        sql.insert_entry(
            connection,
            transaction_id=transaction_id,
            account_id=int(account["id"]),
            entry_type="withdrawal",
            amount_krw=amount_krw,
            counterparty_account_number=None,
            memo=memo,
        )
    return {"transaction_id": transaction_id, "balance_krw": balance}


def transfer(
    engine: Engine,
    sender_user_id: int,
    recipient_account_number: str,
    amount_krw: int,
    memo: str,
) -> dict[str, object]:
    transaction_id = str(uuid4())
    with engine.begin() as connection:
        sender = account_by_user_id(connection, sender_user_id)
        if sender is None:
            raise TransactionError(404, "account not found")
        recipient = account_by_number(connection, recipient_account_number)
        if recipient is None:
            raise TransactionError(404, "recipient account not found")
        if int(sender["id"]) == int(recipient["id"]):
            raise TransactionError(422, "cannot transfer to your own account")

        sender_balance = debit_user_account(connection, sender_user_id, amount_krw)
        if sender_balance is None:
            raise TransactionError(409, "insufficient funds")
        credit_user_account(connection, int(recipient["owner_user_id"]), amount_krw)
        sql.insert_entry(
            connection,
            transaction_id=transaction_id,
            account_id=int(sender["id"]),
            entry_type="transfer_out",
            amount_krw=amount_krw,
            counterparty_account_number=str(recipient["account_number"]),
            memo=memo,
        )
        sql.insert_entry(
            connection,
            transaction_id=transaction_id,
            account_id=int(recipient["id"]),
            entry_type="transfer_in",
            amount_krw=amount_krw,
            counterparty_account_number=str(sender["account_number"]),
            memo=memo,
        )
    return {"transaction_id": transaction_id, "balance_krw": sender_balance}


def record_internal_entry(
    connection: Connection,
    *,
    account_id: int,
    entry_type: Literal["loan_disbursement", "loan_repayment"],
    amount_krw: int,
    memo: str,
) -> str:
    transaction_id = str(uuid4())
    sql.insert_entry(
        connection,
        transaction_id=transaction_id,
        account_id=account_id,
        entry_type=entry_type,
        amount_krw=amount_krw,
        counterparty_account_number=None,
        memo=memo,
    )
    return transaction_id


def transaction_history(
    engine: Engine,
    user_id: int,
    *,
    limit: int,
    offset: int,
) -> list[dict[str, object]]:
    account_id = _account_id(engine, user_id)
    with engine.connect() as connection:
        return sql.list_entries(connection, account_id, limit=limit, offset=offset)


def recipients(
    engine: Engine,
    owner_user_id: int,
    query: str | None,
    limit: int,
) -> list[dict[str, object]]:
    with engine.connect() as connection:
        found = sql.search_recipients(
            connection,
            owner_user_id=owner_user_id,
            query=query,
            limit=limit,
        )
    return [
        {
            "user_id": int(row["user_id"]),
            "name": str(row["name"]),
            "phone_number_masked": f"{'*' * max(0, len(str(row['phone_number'])) - 4)}"
            f"{str(row['phone_number'])[-4:]}",
            "account_number": str(row["account_number"]),
        }
        for row in found
    ]
