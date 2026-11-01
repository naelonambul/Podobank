from sqlalchemy.engine import Connection, Engine

from podobank_api.features.accounts import sql


def create_default_account(connection: Connection, user_id: int) -> dict[str, int | str]:
    existing = account_by_user_id(connection, user_id)
    if existing:
        return existing

    account_number = f"100{user_id:010d}"
    sql.insert_default_account(connection, user_id, account_number)
    account = account_by_user_id(connection, user_id)
    if account is None:
        raise RuntimeError("default account could not be created")
    return account


def account_by_user_id(
    connection: Connection,
    user_id: int,
) -> dict[str, int | str] | None:
    return sql.account_for_user(connection, user_id)


def account_by_number(
    connection: Connection,
    account_number: str,
) -> dict[str, int | str] | None:
    return sql.account_for_number(connection, account_number)


def get_account_for_user(engine: Engine, user_id: int) -> dict[str, int | str] | None:
    with engine.connect() as connection:
        return account_by_user_id(connection, user_id)


def credit_user_account(connection: Connection, user_id: int, amount_krw: int) -> int:
    account = account_by_user_id(connection, user_id)
    if account is None:
        raise LookupError("account not found")
    return sql.credit_account(connection, int(account["id"]), amount_krw)


def debit_user_account(connection: Connection, user_id: int, amount_krw: int) -> int | None:
    account = account_by_user_id(connection, user_id)
    if account is None:
        raise LookupError("account not found")
    return sql.debit_account(connection, int(account["id"]), amount_krw)
