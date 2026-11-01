import secrets
from dataclasses import dataclass

from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from podobank_api.features.accounts import sql

ACCOUNT_NUMBER_ATTEMPTS = 5


class AccountProvisioningError(RuntimeError):
    """Raised when a unique default account number cannot be allocated."""


@dataclass(frozen=True)
class AccountSummary:
    id: int
    account_number: str
    balance: int


def generate_account_number() -> str:
    return str(secrets.randbelow(900_000_000_000) + 100_000_000_000)


def ensure_default_account(connection: Connection, owner_user_id: int) -> dict[str, object]:
    existing = sql.find_account_by_owner(connection, owner_user_id)
    if existing is not None:
        return existing

    for _ in range(ACCOUNT_NUMBER_ATTEMPTS):
        account_number = generate_account_number()
        try:
            with connection.begin_nested():
                account_id = sql.insert_account(
                    connection,
                    owner_user_id=owner_user_id,
                    account_number=account_number,
                )
        except IntegrityError:
            existing = sql.find_account_by_owner(connection, owner_user_id)
            if existing is not None:
                return existing
            if sql.account_number_exists(connection, account_number):
                continue
            raise
        return {
            "id": account_id,
            "owner_user_id": owner_user_id,
            "account_number": account_number,
            "balance": 0,
        }

    raise AccountProvisioningError("could not allocate a unique account number")


class AccountService:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_for_user(self, owner_user_id: int) -> AccountSummary:
        with self._engine.connect() as connection:
            account = sql.find_account_by_owner(connection, owner_user_id)
        if account is None:
            raise LookupError("customer account was not found")
        return AccountSummary(
            id=int(account["id"]),
            account_number=str(account["account_number"]),
            balance=int(account["balance"]),
        )
