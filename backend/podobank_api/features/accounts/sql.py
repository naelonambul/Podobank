from sqlalchemy import text
from sqlalchemy.engine import Connection


def find_account_by_owner(connection: Connection, owner_user_id: int) -> dict[str, object] | None:
    row = (
        connection.execute(
            text(
                "SELECT id, owner_user_id, account_number, balance "
                "FROM accounts WHERE owner_user_id = :owner_user_id"
            ),
            {"owner_user_id": owner_user_id},
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


def account_number_exists(connection: Connection, account_number: str) -> bool:
    return (
        connection.execute(
            text("SELECT 1 FROM accounts WHERE account_number = :account_number"),
            {"account_number": account_number},
        ).first()
        is not None
    )


def insert_account(
    connection: Connection,
    *,
    owner_user_id: int,
    account_number: str,
) -> int:
    result = connection.execute(
        text(
            "INSERT INTO accounts (owner_user_id, account_number, balance) "
            "VALUES (:owner_user_id, :account_number, 0)"
        ),
        {"owner_user_id": owner_user_id, "account_number": account_number},
    )
    if result.lastrowid is None:
        raise RuntimeError("MariaDB did not return the new account ID")
    return int(result.lastrowid)
