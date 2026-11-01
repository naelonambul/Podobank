import re
import secrets
from dataclasses import dataclass
from datetime import datetime

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


@dataclass(frozen=True)
class RecipientSummary:
    account_id: int
    name: str
    masked_account_number: str
    phone_suffix: str


@dataclass(frozen=True)
class LedgerEntry:
    entry_id: int
    posted_at: datetime
    transaction_id: str
    account_id: int
    entry_type: str
    amount: int


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

    def find_recipients(
        self,
        *,
        current_user_id: int,
        query: str | None,
        limit: int,
        offset: int,
    ) -> list[RecipientSummary]:
        normalized_query = _normalize_recipient_query(query) if query is not None else None
        with self._engine.connect() as connection:
            rows = sql.find_recipients(
                connection,
                exclude_user_id=current_user_id,
                query=normalized_query,
                limit=limit,
                offset=offset,
            )
        return [
            RecipientSummary(
                account_id=int(row["account_id"]),
                name=str(row["name"]),
                masked_account_number=f"••••{str(row['account_number'])[-4:]}",
                phone_suffix=str(row["phone_number"])[-4:],
            )
            for row in rows
        ]

    def get_ledger_for_user(
        self,
        *,
        owner_user_id: int,
        start_at: datetime | None,
        end_at: datetime | None,
        limit: int,
        offset: int,
    ) -> list[LedgerEntry]:
        with self._engine.connect() as connection:
            account = sql.find_account_by_owner(connection, owner_user_id)
            if account is None:
                raise LookupError("customer account was not found")
            rows = sql.list_ledger_entries(
                connection,
                account_id=int(account["id"]),
                start_at=start_at,
                end_at=end_at,
                limit=limit,
                offset=offset,
            )
        return [
            LedgerEntry(
                entry_id=int(row["entry_id"]),
                posted_at=row["posted_at"],
                transaction_id=str(row["transaction_id"]),
                account_id=int(row["account_id"]),
                entry_type=str(row["entry_type"]),
                amount=int(row["amount"]),
            )
            for row in rows
        ]


def _normalize_recipient_query(query: str) -> str:
    if not re.fullmatch(r"[0-9+() .-]+", query):
        raise ValueError("recipient query must be an account number or phone number")
    normalized = re.sub(r"[+() .-]", "", query)
    if not 10 <= len(normalized) <= 32:
        raise ValueError("recipient query must be an account number or phone number")
    return normalized
