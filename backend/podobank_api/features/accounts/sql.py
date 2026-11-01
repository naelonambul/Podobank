from sqlalchemy.engine import Connection


def account_for_user(connection: Connection, user_id: int) -> dict[str, int | str] | None:
    row = connection.exec_driver_sql(
        "SELECT id, owner_user_id, account_number, balance_krw "
        "FROM accounts WHERE owner_user_id = ?",
        (user_id,),
    ).first()
    return dict(row._mapping) if row else None


def account_for_number(connection: Connection, account_number: str) -> dict[str, int | str] | None:
    row = connection.exec_driver_sql(
        "SELECT id, owner_user_id, account_number, balance_krw "
        "FROM accounts WHERE account_number = ?",
        (account_number,),
    ).first()
    return dict(row._mapping) if row else None


def insert_default_account(connection: Connection, user_id: int, account_number: str) -> None:
    connection.exec_driver_sql(
        "INSERT INTO accounts (owner_user_id, account_number) VALUES (?, ?) "
        "ON CONFLICT (owner_user_id) DO NOTHING",
        (user_id, account_number),
    )


def credit_account(connection: Connection, account_id: int, amount_krw: int) -> int:
    result = connection.exec_driver_sql(
        "UPDATE accounts SET balance_krw = balance_krw + ? WHERE id = ?",
        (amount_krw, account_id),
    )
    if result.rowcount != 1:
        raise LookupError("account not found")
    balance = connection.exec_driver_sql(
        "SELECT balance_krw FROM accounts WHERE id = ?",
        (account_id,),
    ).scalar_one()
    return int(balance)


def debit_account(connection: Connection, account_id: int, amount_krw: int) -> int | None:
    result = connection.exec_driver_sql(
        "UPDATE accounts SET balance_krw = balance_krw - ? WHERE id = ? AND balance_krw >= ?",
        (amount_krw, account_id, amount_krw),
    )
    if result.rowcount != 1:
        exists = connection.exec_driver_sql(
            "SELECT 1 FROM accounts WHERE id = ?",
            (account_id,),
        ).first()
        if not exists:
            raise LookupError("account not found")
        return None
    balance = connection.exec_driver_sql(
        "SELECT balance_krw FROM accounts WHERE id = ?",
        (account_id,),
    ).scalar_one()
    return int(balance)
