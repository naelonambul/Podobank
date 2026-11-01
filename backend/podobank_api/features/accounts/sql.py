from datetime import datetime

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


def find_recipients(
    connection: Connection,
    *,
    exclude_user_id: int,
    query: str | None,
    limit: int,
    offset: int,
) -> list[dict[str, object]]:
    query_filter = ""
    parameters: dict[str, object] = {
        "exclude_user_id": exclude_user_id,
        "limit": limit,
        "offset": offset,
    }
    if query is not None:
        query_filter = "AND (a.account_number = :account_query OR u.phone_number = :phone_query)"
        parameters["account_query"] = query
        parameters["phone_query"] = query if 10 <= len(query) <= 15 else ""

    rows = connection.execute(
        text(
            "SELECT a.id AS account_id, a.account_number, u.name, u.phone_number "
            "FROM accounts AS a JOIN users AS u ON u.id = a.owner_user_id "
            "WHERE u.role = 'customer' AND u.id <> :exclude_user_id "
            f"{query_filter} "
            "ORDER BY u.name, a.id LIMIT :limit OFFSET :offset"
        ),
        parameters,
    ).mappings()
    return [dict(row) for row in rows]


def list_ledger_entries(
    connection: Connection,
    *,
    account_id: int,
    start_at: datetime | None,
    end_at: datetime | None,
    limit: int,
    offset: int,
) -> list[dict[str, object]]:
    date_filter = ""
    parameters: dict[str, object] = {
        "account_id": account_id,
        "limit": limit,
        "offset": offset,
    }
    if start_at is not None:
        date_filter += " AND posted_at >= :start_at"
        parameters["start_at"] = start_at
    if end_at is not None:
        date_filter += " AND posted_at <= :end_at"
        parameters["end_at"] = end_at

    row_count = int(
        connection.execute(
            text(
                f"SELECT COUNT(*) FROM ledger_entries WHERE account_id = :account_id {date_filter}"
            ),
            parameters,
        ).scalar_one()
    )
    page_size = min(limit, row_count - offset)
    if page_size <= 0:
        return []
    ascending_offset = row_count - offset - page_size
    page_parameters = {
        **parameters,
        "limit": page_size,
        "offset": ascending_offset,
    }
    rows = connection.execute(
        text(
            "SELECT entry_id, posted_at, transaction_id, account_id, entry_type, amount "
            "FROM ledger_entries WHERE account_id = :account_id "
            f"{date_filter} "
            "ORDER BY posted_at, entry_id LIMIT :limit OFFSET :offset"
        ),
        page_parameters,
    ).mappings()
    return [dict(row) for row in reversed(list(rows))]
