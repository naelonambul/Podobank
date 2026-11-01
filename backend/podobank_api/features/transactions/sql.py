from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection


def find_account_id_by_owner(connection: Connection, owner_user_id: int) -> int | None:
    account_id = connection.execute(
        text("SELECT id FROM accounts WHERE owner_user_id = :owner_user_id"),
        {"owner_user_id": owner_user_id},
    ).scalar_one_or_none()
    return int(account_id) if account_id is not None else None


def lock_account_by_owner(connection: Connection, owner_user_id: int) -> dict[str, object] | None:
    row = (
        connection.execute(
            text(
                "SELECT id, owner_user_id, balance FROM accounts "
                "WHERE owner_user_id = :owner_user_id FOR UPDATE WAIT 3"
            ),
            {"owner_user_id": owner_user_id},
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


def lock_account_by_id(connection: Connection, account_id: int) -> dict[str, object] | None:
    row = (
        connection.execute(
            text(
                "SELECT id, owner_user_id, balance FROM accounts "
                "WHERE id = :account_id FOR UPDATE WAIT 3"
            ),
            {"account_id": account_id},
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


def is_customer_user(connection: Connection, user_id: int) -> bool:
    return (
        connection.execute(
            text("SELECT 1 FROM users WHERE id = :user_id AND role = 'customer'"),
            {"user_id": user_id},
        ).first()
        is not None
    )


def add_balance(connection: Connection, *, account_id: int, delta: int) -> None:
    result = connection.execute(
        text("UPDATE accounts SET balance = balance + :delta WHERE id = :account_id"),
        {"account_id": account_id, "delta": delta},
    )
    if result.rowcount != 1:
        raise RuntimeError("locked account disappeared during money movement")


def insert_ledger_entry(
    connection: Connection,
    *,
    posted_at: datetime,
    transaction_id: str,
    account_id: int,
    user_id: int,
    entry_type: str,
    amount: int,
) -> None:
    connection.execute(
        text(
            "INSERT INTO ledger_entries "
            "(posted_at, transaction_id, account_id, user_id, entry_type, amount) "
            "VALUES (:posted_at, :transaction_id, :account_id, :user_id, :entry_type, :amount)"
        ),
        {
            "posted_at": posted_at,
            "transaction_id": transaction_id,
            "account_id": account_id,
            "user_id": user_id,
            "entry_type": entry_type,
            "amount": amount,
        },
    )
