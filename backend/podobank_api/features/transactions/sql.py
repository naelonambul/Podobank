import re

from sqlalchemy.engine import Connection


def insert_entry(
    connection: Connection,
    *,
    transaction_id: str,
    account_id: int,
    entry_type: str,
    amount_krw: int,
    counterparty_account_number: str | None,
    memo: str,
) -> None:
    connection.exec_driver_sql(
        "INSERT INTO transaction_entries (transaction_id, account_id, entry_type, amount_krw, "
        "counterparty_account_number, memo) VALUES (?, ?, ?, ?, ?, ?)",
        (
            transaction_id,
            account_id,
            entry_type,
            amount_krw,
            counterparty_account_number,
            memo,
        ),
    )


def list_entries(
    connection: Connection,
    account_id: int,
    *,
    limit: int,
    offset: int,
) -> list[dict[str, object]]:
    rows = connection.exec_driver_sql(
        "SELECT transaction_id, entry_type, amount_krw, counterparty_account_number, memo, "
        "created_at FROM transaction_entries WHERE account_id = ? "
        "ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
        (account_id, limit, offset),
    ).all()
    return [dict(row._mapping) for row in rows]


def search_recipients(
    connection: Connection,
    *,
    owner_user_id: int,
    query: str | None,
    limit: int,
) -> list[dict[str, object]]:
    if query:
        pattern = f"%{query}%"
        phone_digits = re.sub(r"[^0-9]", "", query)
        phone_pattern = f"%{phone_digits}%" if phone_digits else None
        search_clauses = ["a.account_number LIKE ?", "u.name LIKE ?"]
        search_values = [pattern, pattern]
        if phone_pattern is not None:
            search_clauses.insert(1, "u.phone_number LIKE ?")
            search_values.insert(1, phone_pattern)
        rows = connection.exec_driver_sql(
            "SELECT u.id AS user_id, u.name, u.phone_number, a.account_number "
            "FROM users AS u JOIN accounts AS a ON a.owner_user_id = u.id "
            "WHERE u.role = 'customer' AND u.id != ? AND ("
            + " OR ".join(search_clauses)
            + ") ORDER BY u.name, a.account_number LIMIT ?",
            (owner_user_id, *search_values, limit),
        ).all()
    else:
        rows = connection.exec_driver_sql(
            "SELECT u.id AS user_id, u.name, u.phone_number, a.account_number "
            "FROM users AS u JOIN accounts AS a ON a.owner_user_id = u.id "
            "WHERE u.role = 'customer' AND u.id != ? "
            "ORDER BY u.name, a.account_number LIMIT ?",
            (owner_user_id, limit),
        ).all()
    return [dict(row._mapping) for row in rows]
