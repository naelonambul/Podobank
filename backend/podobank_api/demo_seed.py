import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

from podobank_api.features.auth.passwords import hash_password
from podobank_api.features.loans.service import repayment_due_dates
from podobank_api.seed import DEMO_ACCOUNT_NUMBER, DEMO_CUSTOMER_PHONE, LOAN_PRODUCTS

DEMO_CUSTOMER_COUNT = 10_000
DEMO_LEDGER_ENTRIES_PER_CUSTOMER = 20
DEMO_LOAN_APPLICATION_COUNT = 500
DEMO_LOAN_STATUS_COUNTS = {
    "pending": 100,
    "rejected": 100,
    "repaying": 250,
    "repaid": 50,
}

_CUSTOMER_PHONE_PREFIX = "010999"
_ACCOUNT_NUMBER_PREFIX = "900000"
_BATCH_SIZE = 500
_TRANSFER_AMOUNT = 1_000
_WITHDRAWAL_AMOUNT = 10_000
_MAX_BALANCE = 9_223_372_036_854_775_807
_ACTIVITY_START = datetime(2026, 1, 1)
_SEED_AS_OF_DATE = date(2026, 11, 2)
_REPAYING_APPROVAL = datetime(2026, 1, 15)
_REPAID_APPROVAL = datetime(2020, 1, 15)
_ID_NAMESPACE = uuid.UUID("cbcae34a-a4a5-47e9-9f63-309a8cf2d651")


@dataclass(frozen=True)
class DemoSeedSummary:
    already_present: bool
    customer_count: int
    account_count: int
    ledger_entry_count: int
    loan_application_count: int
    repayment_count: int


@dataclass(frozen=True)
class _LoanSeed:
    customer_index: int
    status: str
    created_at: datetime
    reviewed_at: datetime | None
    approved_at: datetime | None
    due_dates: tuple[date, ...]
    repayment_statuses: tuple[str, ...]

    @property
    def paid_installment_numbers(self) -> tuple[int, ...]:
        return tuple(
            index
            for index, status in enumerate(self.repayment_statuses, start=1)
            if status == "paid"
        )


def _transaction_id(kind: str, customer_index: int, item_index: int = 0) -> str:
    return str(
        uuid.uuid5(
            _ID_NAMESPACE,
            f"podobank-demo:{kind}:{customer_index}:{item_index}",
        )
    )


def _customer_phone(customer_index: int) -> str:
    return f"{_CUSTOMER_PHONE_PREFIX}{customer_index:05d}"


def _customer_account_number(customer_index: int) -> str:
    return f"{_ACCOUNT_NUMBER_PREFIX}{customer_index:06d}"


def _generated_customer(customer_index: int) -> dict[str, object]:
    return {
        "name": f"샘플 고객 {customer_index:05d}",
        "phone_number": _customer_phone(customer_index),
        "age": 20 + customer_index % 50,
        "gender": "female" if customer_index % 2 else "male",
        "marital_status": "married" if customer_index % 3 == 0 else "single",
        "is_employed": 0 if customer_index % 5 == 0 else 1,
        "role": "customer",
    }


def _loan_statuses(loan_application_count: int) -> tuple[str, ...]:
    if loan_application_count == 0:
        return ()
    if loan_application_count % 10:
        raise ValueError("loan_application_count must be zero or a multiple of 10")

    scale = loan_application_count // 10
    counts = {status: count * scale // 50 for status, count in DEMO_LOAN_STATUS_COUNTS.items()}
    # Keep the fixed demo customer in the repaying state for the sample login.
    statuses = ["repaying"]
    for status in ("pending", "rejected", "repaying", "repaid"):
        statuses.extend([status] * (counts[status] - (status == "repaying")))
    return tuple(statuses)


def _loan_seeds(loan_application_count: int) -> tuple[_LoanSeed, ...]:
    statuses = _loan_statuses(loan_application_count)
    result: list[_LoanSeed] = []
    term_months = int(LOAN_PRODUCTS[0]["term_months"])
    for customer_index, status in enumerate(statuses):
        if status == "pending":
            created_at = datetime(2026, 10, 15) - timedelta(days=customer_index)
            result.append(_LoanSeed(customer_index, status, created_at, None, None, (), ()))
        elif status == "rejected":
            reviewed_at = datetime(2025, 7, 1) + timedelta(days=customer_index)
            result.append(
                _LoanSeed(
                    customer_index,
                    status,
                    reviewed_at - timedelta(days=14),
                    reviewed_at,
                    None,
                    (),
                    (),
                )
            )
        else:
            approved_at = _REPAYING_APPROVAL if status == "repaying" else _REPAID_APPROVAL
            due_dates = tuple(repayment_due_dates(approved_at, term_months))
            if status == "repaid":
                repayment_statuses = ("paid",) * term_months
            else:
                overdue_due_dates = [
                    due_date for due_date in due_dates if due_date < _SEED_AS_OF_DATE
                ]
                if len(overdue_due_dates) < 2:
                    raise ValueError(
                        "the demo repayment schedule must include overdue installments"
                    )
                paid_count = len(overdue_due_dates) - 2
                repayment_statuses = tuple(
                    "paid"
                    if installment <= paid_count
                    else "overdue"
                    if due_date < _SEED_AS_OF_DATE
                    else "scheduled"
                    for installment, due_date in enumerate(due_dates, start=1)
                )
            result.append(
                _LoanSeed(
                    customer_index,
                    status,
                    approved_at - timedelta(days=14),
                    approved_at,
                    approved_at,
                    due_dates,
                    repayment_statuses,
                )
            )
    return tuple(result)


def _expected_transaction_counts(
    customer_count: int,
    transfer_count_per_customer: int,
    loan_seeds: tuple[_LoanSeed, ...],
) -> dict[str, int]:
    expected: dict[str, int] = {}
    for customer_index in range(customer_count):
        expected[_transaction_id("deposit", customer_index)] = 1
        expected[_transaction_id("withdrawal", customer_index)] = 1
        for transfer_index in range(transfer_count_per_customer):
            expected[_transaction_id("transfer", customer_index, transfer_index)] = 2
    for loan_seed in loan_seeds:
        if loan_seed.approved_at is None:
            continue
        expected[_transaction_id("loan-disbursement", loan_seed.customer_index)] = 1
        for installment_number in loan_seed.paid_installment_numbers:
            expected[
                _transaction_id(
                    "loan-repayment",
                    loan_seed.customer_index,
                    installment_number,
                )
            ] = 1
    return expected


def _existing_transaction_counts(
    connection: Connection,
    expected_transaction_counts: dict[str, int],
) -> dict[str, int]:
    transaction_ids = list(expected_transaction_counts)
    statement = text(
        "SELECT transaction_id, COUNT(*) AS entry_count FROM ledger_entries "
        "WHERE transaction_id IN :transaction_ids GROUP BY transaction_id"
    ).bindparams(bindparam("transaction_ids", expanding=True))
    actual: dict[str, int] = {}
    for offset in range(0, len(transaction_ids), _BATCH_SIZE):
        batch = transaction_ids[offset : offset + _BATCH_SIZE]
        for row in connection.execute(statement, {"transaction_ids": batch}).all():
            actual[str(row.transaction_id)] = int(row.entry_count)
    return actual


def _execute_batches(
    connection: Connection,
    statement: str,
    rows: Iterable[dict[str, object]],
) -> None:
    batch: list[dict[str, object]] = []
    for row in rows:
        batch.append(row)
        if len(batch) == _BATCH_SIZE:
            connection.execute(text(statement), batch)
            batch.clear()
    if batch:
        connection.execute(text(statement), batch)


def _base_ledger_entries(
    customers: list[dict[str, object]],
    account_ids: dict[int, int],
    transfer_count_per_customer: int,
) -> Iterator[dict[str, object]]:
    customer_count = len(customers)
    for customer_index, customer in enumerate(customers):
        account_id = account_ids[customer_index]
        user_id = int(customer["id"])
        activity_at = _ACTIVITY_START + timedelta(minutes=customer_index * 10)
        yield {
            "posted_at": activity_at,
            "transaction_id": _transaction_id("deposit", customer_index),
            "account_id": account_id,
            "user_id": user_id,
            "entry_type": "deposit",
            "amount": 100_000 + customer_index * 1_000,
        }
        yield {
            "posted_at": activity_at + timedelta(minutes=1),
            "transaction_id": _transaction_id("withdrawal", customer_index),
            "account_id": account_id,
            "user_id": user_id,
            "entry_type": "withdrawal",
            "amount": -_WITHDRAWAL_AMOUNT,
        }
        for transfer_index in range(transfer_count_per_customer):
            destination_index = (customer_index + transfer_index + 1) % customer_count
            posted_at = activity_at + timedelta(minutes=2 + transfer_index)
            transaction_id = _transaction_id("transfer", customer_index, transfer_index)
            yield {
                "posted_at": posted_at,
                "transaction_id": transaction_id,
                "account_id": account_id,
                "user_id": user_id,
                "entry_type": "transfer_out",
                "amount": -_TRANSFER_AMOUNT,
            }
            destination = customers[destination_index]
            yield {
                "posted_at": posted_at,
                "transaction_id": transaction_id,
                "account_id": account_ids[destination_index],
                "user_id": int(destination["id"]),
                "entry_type": "transfer_in",
                "amount": _TRANSFER_AMOUNT,
            }


def _loan_ledger_entries(
    loan_seeds: tuple[_LoanSeed, ...],
    applications: dict[int, int],
    customers: list[dict[str, object]],
    account_ids: dict[int, int],
) -> Iterator[dict[str, object]]:
    monthly_installment = int(LOAN_PRODUCTS[0]["monthly_installment"])
    principal_amount = int(LOAN_PRODUCTS[0]["principal_amount"])
    for loan_seed in loan_seeds:
        if loan_seed.approved_at is None:
            continue
        customer_index = loan_seed.customer_index
        customer = customers[customer_index]
        yield {
            "posted_at": loan_seed.approved_at,
            "transaction_id": _transaction_id("loan-disbursement", customer_index),
            "account_id": account_ids[customer_index],
            "user_id": int(customer["id"]),
            "entry_type": "loan_disbursement",
            "amount": principal_amount,
        }
        for installment_number in loan_seed.paid_installment_numbers:
            due_date = loan_seed.due_dates[installment_number - 1]
            yield {
                "posted_at": datetime.combine(due_date, time(hour=12)),
                "transaction_id": _transaction_id(
                    "loan-repayment", customer_index, installment_number
                ),
                "account_id": account_ids[customer_index],
                "user_id": int(customer["id"]),
                "entry_type": "loan_repayment",
                "amount": -monthly_installment,
            }


def _loan_application_rows(
    loan_seeds: tuple[_LoanSeed, ...],
    customers: list[dict[str, object]],
    employee_id: int,
    product_id: int,
) -> list[dict[str, object]]:
    product = LOAN_PRODUCTS[0]
    result: list[dict[str, object]] = []
    for loan_seed in loan_seeds:
        row: dict[str, object] = {
            "user_id": int(customers[loan_seed.customer_index]["id"]),
            "product_id": product_id,
            "product_code": product["code"],
            "product_name": product["name"],
            "principal_amount": product["principal_amount"],
            "term_months": product["term_months"],
            "monthly_installment": product["monthly_installment"],
            "status": loan_seed.status,
            "created_at": loan_seed.created_at,
            "reviewed_at": loan_seed.reviewed_at,
            "reviewed_by": employee_id if loan_seed.reviewed_at is not None else None,
            "approved_at": loan_seed.approved_at,
        }
        result.append(row)
    return result


def _repayment_rows(
    loan_seeds: tuple[_LoanSeed, ...],
    applications: dict[int, int],
) -> Iterator[dict[str, object]]:
    amount = int(LOAN_PRODUCTS[0]["monthly_installment"])
    for loan_seed in loan_seeds:
        application_id = applications.get(loan_seed.customer_index)
        if application_id is None:
            continue
        for installment_number, (due_date, status) in enumerate(
            zip(loan_seed.due_dates, loan_seed.repayment_statuses, strict=True),
            start=1,
        ):
            processed_at = None
            paid_at = None
            if status == "paid":
                processed_at = datetime.combine(due_date, time(hour=12))
                paid_at = processed_at
            elif status == "overdue":
                processed_at = datetime.combine(_SEED_AS_OF_DATE, time(hour=12))
            yield {
                "loan_application_id": application_id,
                "installment_number": installment_number,
                "due_date": due_date,
                "amount": amount,
                "status": status,
                "processed_at": processed_at,
                "paid_at": paid_at,
            }


def _summary(
    *,
    already_present: bool,
    customer_count: int,
    account_count: int,
    expected_transaction_counts: dict[str, int],
    loan_seeds: tuple[_LoanSeed, ...],
) -> DemoSeedSummary:
    return DemoSeedSummary(
        already_present=already_present,
        customer_count=customer_count,
        account_count=account_count,
        ledger_entry_count=sum(expected_transaction_counts.values()),
        loan_application_count=len(loan_seeds),
        repayment_count=sum(len(loan_seed.due_dates) for loan_seed in loan_seeds),
    )


def _validate_parameters(
    *,
    demo_customer_password: str,
    customer_count: int,
    ledger_entries_per_customer: int,
    loan_application_count: int,
) -> int:
    if not demo_customer_password or len(demo_customer_password) < 8:
        raise ValueError("a demo customer password of at least 8 characters is required")
    if customer_count < 2:
        raise ValueError("customer_count must include the fixed demo customer and another customer")
    if ledger_entries_per_customer < 4 or ledger_entries_per_customer % 2:
        raise ValueError("ledger_entries_per_customer must be an even number of at least 4")
    transfer_count = (ledger_entries_per_customer - 2) // 2
    if transfer_count >= customer_count:
        raise ValueError("customer_count must exceed the per-customer transfer count")
    if loan_application_count < 0 or loan_application_count > customer_count:
        raise ValueError("loan_application_count must be between zero and customer_count")
    if loan_application_count and loan_application_count % 10:
        raise ValueError("loan_application_count must be zero or a multiple of 10")
    return transfer_count


def _load_demo_customer(connection: Connection) -> dict[str, object]:
    customer = (
        connection.execute(
            text("SELECT id, role, password_hash FROM users WHERE phone_number = :phone_number"),
            {"phone_number": DEMO_CUSTOMER_PHONE},
        )
        .mappings()
        .one_or_none()
    )
    if customer is None or customer["role"] != "customer":
        raise ValueError("initialize the database with the default demo customer before seeding")
    account = (
        connection.execute(
            text(
                "SELECT id, owner_user_id, balance FROM accounts "
                "WHERE account_number = :account_number"
            ),
            {"account_number": DEMO_ACCOUNT_NUMBER},
        )
        .mappings()
        .one_or_none()
    )
    if account is None or int(account["owner_user_id"]) != int(customer["id"]):
        raise ValueError("initialize the database with the default demo account before seeding")
    return {**dict(customer), "account_id": int(account["id"]), "balance": int(account["balance"])}


def _load_generated_customers(
    connection: Connection,
    expected_count: int,
) -> list[dict[str, object]]:
    rows = connection.execute(
        text(
            "SELECT id, name, phone_number, age, gender, marital_status, is_employed, role "
            "FROM users WHERE phone_number LIKE :phone_prefix ORDER BY phone_number"
        ),
        {"phone_prefix": f"{_CUSTOMER_PHONE_PREFIX}%"},
    ).mappings()
    existing = [dict(row) for row in rows]
    expected = [_generated_customer(index) for index in range(1, expected_count + 1)]
    expected_by_phone = {str(row["phone_number"]): row for row in expected}
    if len(existing) > expected_count or any(
        str(row["phone_number"]) not in expected_by_phone
        or any(
            row[column] != expected_by_phone[str(row["phone_number"])][column]
            for column in expected_by_phone[str(row["phone_number"])]
        )
        for row in existing
    ):
        raise ValueError("the demo customer phone namespace contains conflicting data")
    return existing


def _load_generated_accounts(connection: Connection) -> list[dict[str, object]]:
    return [
        dict(row)
        for row in connection.execute(
            text(
                "SELECT a.id, a.owner_user_id, a.account_number, a.balance "
                "FROM accounts AS a WHERE a.account_number LIKE :account_prefix "
                "ORDER BY a.account_number"
            ),
            {"account_prefix": f"{_ACCOUNT_NUMBER_PREFIX}%"},
        ).mappings()
    ]


def _load_loan_applications(
    connection: Connection,
    customer_ids: list[int],
) -> list[dict[str, object]]:
    if not customer_ids:
        return []
    statement = text(
        "SELECT id, user_id, product_code, principal_amount, term_months, "
        "monthly_installment, status FROM loan_applications WHERE user_id IN :user_ids"
    ).bindparams(bindparam("user_ids", expanding=True))
    result: list[dict[str, object]] = []
    for offset in range(0, len(customer_ids), _BATCH_SIZE):
        user_batch = customer_ids[offset : offset + _BATCH_SIZE]
        result.extend(
            dict(row) for row in connection.execute(statement, {"user_ids": user_batch}).mappings()
        )
    return result


def _verify_complete_seed(
    connection: Connection,
    *,
    demo_customer: dict[str, object],
    generated_customers: list[dict[str, object]],
    generated_accounts: list[dict[str, object]],
    expected_customer_count: int,
    sample_customers: list[dict[str, object]],
    loan_seeds: tuple[_LoanSeed, ...],
    loan_applications: list[dict[str, object]],
    expected_transaction_counts: dict[str, int],
    actual_transaction_counts: dict[str, int],
) -> bool:
    generated_count = expected_customer_count - 1
    if len(sample_customers) != expected_customer_count:
        return False
    if len(generated_customers) != generated_count or len(generated_accounts) != generated_count:
        return False

    generated_by_phone = {str(row["phone_number"]): row for row in generated_customers}
    accounts_by_owner = {int(row["owner_user_id"]): row for row in generated_accounts}
    for customer_index in range(1, generated_count + 1):
        customer = generated_by_phone.get(_customer_phone(customer_index))
        if customer is None:
            return False
        account = accounts_by_owner.get(int(customer["id"]))
        if account is None or account["account_number"] != _customer_account_number(customer_index):
            return False

    if len(generated_by_phone) != generated_count:
        return False
    if actual_transaction_counts != expected_transaction_counts:
        return False

    if len(loan_applications) != len(loan_seeds):
        return False
    status_by_customer = {int(row["user_id"]): str(row["status"]) for row in loan_applications}
    expected_status_by_customer = {
        int(sample_customers[loan_seed.customer_index]["id"]): loan_seed.status
        for loan_seed in loan_seeds
    }
    if status_by_customer != expected_status_by_customer:
        return False
    if any(
        row["product_code"] != LOAN_PRODUCTS[0]["code"]
        or int(row["principal_amount"]) != int(LOAN_PRODUCTS[0]["principal_amount"])
        or int(row["term_months"]) != int(LOAN_PRODUCTS[0]["term_months"])
        or int(row["monthly_installment"]) != int(LOAN_PRODUCTS[0]["monthly_installment"])
        for row in loan_applications
    ):
        return False

    expected_repayment_count = sum(len(loan_seed.due_dates) for loan_seed in loan_seeds)
    if loan_applications:
        repayment_count = connection.execute(
            text(
                "SELECT COUNT(*) FROM loan_repayments WHERE loan_application_id IN "
                "(SELECT id FROM loan_applications WHERE user_id IN :user_ids)"
            ).bindparams(bindparam("user_ids", expanding=True)),
            {"user_ids": [int(customer["id"]) for customer in sample_customers]},
        ).scalar_one()
    else:
        repayment_count = 0
    if int(repayment_count) != expected_repayment_count:
        return False

    account_ids = [int(demo_customer["account_id"])] + [
        int(row["id"]) for row in generated_accounts
    ]
    account_sums = connection.execute(
        text(
            "SELECT a.id, a.balance, COALESCE(SUM(l.amount), 0) AS ledger_balance "
            "FROM accounts AS a LEFT JOIN ledger_entries AS l ON l.account_id = a.id "
            "WHERE a.id IN :account_ids GROUP BY a.id, a.balance"
        ).bindparams(bindparam("account_ids", expanding=True)),
        {"account_ids": account_ids},
    ).all()
    return len(account_sums) == len(account_ids) and all(
        int(row.balance) == int(row.ledger_balance) for row in account_sums
    )


def seed_demo_data(
    connection: Connection,
    *,
    demo_customer_password: str,
    customer_count: int = DEMO_CUSTOMER_COUNT,
    ledger_entries_per_customer: int = DEMO_LEDGER_ENTRIES_PER_CUSTOMER,
    loan_application_count: int = DEMO_LOAN_APPLICATION_COUNT,
) -> DemoSeedSummary:
    """Insert a deterministic local demo dataset into the caller's transaction."""
    transfer_count = _validate_parameters(
        demo_customer_password=demo_customer_password,
        customer_count=customer_count,
        ledger_entries_per_customer=ledger_entries_per_customer,
        loan_application_count=loan_application_count,
    )
    demo_customer = _load_demo_customer(connection)
    generated_customers = _load_generated_customers(connection, customer_count - 1)
    generated_accounts = _load_generated_accounts(connection)
    sample_customer_ids = [int(demo_customer["id"])] + [
        int(row["id"]) for row in generated_customers
    ]
    existing_applications = _load_loan_applications(connection, sample_customer_ids)
    loan_seeds = _loan_seeds(loan_application_count)
    expected_transaction_counts = _expected_transaction_counts(
        customer_count,
        transfer_count,
        loan_seeds,
    )
    actual_transaction_counts = _existing_transaction_counts(
        connection,
        expected_transaction_counts,
    )
    sample_evidence = bool(
        generated_customers
        or generated_accounts
        or existing_applications
        or actual_transaction_counts
    )

    if sample_evidence:
        customer_rows = [
            {
                "id": int(demo_customer["id"]),
                "name": "가상 고객 1",
                "phone_number": DEMO_CUSTOMER_PHONE,
            }
        ]
        customer_rows.extend(generated_customers)
        complete = _verify_complete_seed(
            connection,
            demo_customer=demo_customer,
            generated_customers=generated_customers,
            generated_accounts=generated_accounts,
            expected_customer_count=customer_count,
            sample_customers=customer_rows,
            loan_seeds=loan_seeds,
            loan_applications=existing_applications,
            expected_transaction_counts=expected_transaction_counts,
            actual_transaction_counts=actual_transaction_counts,
        )
        if not complete:
            raise ValueError(
                "the demo sample namespace is partial or conflicting; reset the local "
                "development database before seeding again"
            )
        return _summary(
            already_present=True,
            customer_count=customer_count,
            account_count=customer_count,
            expected_transaction_counts=expected_transaction_counts,
            loan_seeds=loan_seeds,
        )

    if generated_accounts:
        raise ValueError("the demo account namespace contains conflicting data")
    if existing_applications:
        raise ValueError("the fixed demo customer already has loan applications")

    fixed_account_balance = int(demo_customer["balance"])
    fixed_account_ledger = int(
        connection.execute(
            text("SELECT COALESCE(SUM(amount), 0) FROM ledger_entries WHERE account_id = :id"),
            {"id": demo_customer["account_id"]},
        ).scalar_one()
    )
    if fixed_account_balance != fixed_account_ledger:
        raise ValueError("the fixed demo account balance does not reconcile with its ledger")

    employee_id = connection.execute(
        text("SELECT id FROM users WHERE role = 'bank_employee' ORDER BY id LIMIT 1")
    ).scalar_one_or_none()
    if employee_id is None:
        raise ValueError("initialize the database with a bank employee before seeding")
    product_id = connection.execute(
        text("SELECT id FROM loan_products WHERE code = :code"),
        {"code": LOAN_PRODUCTS[0]["code"]},
    ).scalar_one_or_none()
    if product_id is None:
        raise ValueError("initialize the database with the default loan products before seeding")

    loan_balance_deltas = {
        loan_seed.customer_index: int(LOAN_PRODUCTS[0]["principal_amount"])
        - int(LOAN_PRODUCTS[0]["monthly_installment"]) * len(loan_seed.paid_installment_numbers)
        for loan_seed in loan_seeds
        if loan_seed.approved_at is not None
    }
    planned_balances = {
        index: 100_000
        + index * 1_000
        - _WITHDRAWAL_AMOUNT
        + loan_balance_deltas.get(index, 0)
        + (fixed_account_balance if index == 0 else 0)
        for index in range(customer_count)
    }
    if any(balance < 0 or balance > _MAX_BALANCE for balance in planned_balances.values()):
        raise ValueError("the demo seed would produce an invalid account balance")

    generated_rows = [_generated_customer(index) for index in range(1, customer_count)]
    _execute_batches(
        connection,
        "INSERT INTO users (name, phone_number, age, gender, marital_status, is_employed, role) "
        "VALUES (:name, :phone_number, :age, :gender, :marital_status, :is_employed, :role)",
        generated_rows,
    )
    inserted_customers = [
        dict(row)
        for row in connection.execute(
            text(
                "SELECT id, name, phone_number, age, gender, marital_status, is_employed, role "
                "FROM users WHERE phone_number LIKE :phone_prefix ORDER BY phone_number"
            ),
            {"phone_prefix": f"{_CUSTOMER_PHONE_PREFIX}%"},
        ).mappings()
    ]
    if len(inserted_customers) != customer_count - 1:
        raise ValueError("not all demo customer records were inserted")

    customers = [
        {"id": int(demo_customer["id"]), "name": "가상 고객 1", "phone_number": DEMO_CUSTOMER_PHONE}
    ] + inserted_customers
    account_rows = [
        {
            "owner_user_id": int(customer["id"]),
            "account_number": _customer_account_number(index),
            "balance": 0,
        }
        for index, customer in enumerate(customers[1:], start=1)
    ]
    _execute_batches(
        connection,
        "INSERT INTO accounts (owner_user_id, account_number, balance) "
        "VALUES (:owner_user_id, :account_number, :balance)",
        account_rows,
    )
    account_rows_by_owner = {
        int(row["owner_user_id"]): dict(row)
        for row in connection.execute(
            text(
                "SELECT id, owner_user_id, account_number, balance FROM accounts "
                "WHERE owner_user_id IN :user_ids"
            ).bindparams(bindparam("user_ids", expanding=True)),
            {"user_ids": [int(customer["id"]) for customer in customers]},
        ).mappings()
    }
    account_ids = {
        index: int(account_rows_by_owner[int(customer["id"])]["id"])
        for index, customer in enumerate(customers)
    }
    customers = [dict(customer) for customer in customers]

    if demo_customer["password_hash"] is None:
        connection.execute(
            text("UPDATE users SET password_hash = :password_hash WHERE id = :user_id"),
            {
                "password_hash": hash_password(demo_customer_password),
                "user_id": demo_customer["id"],
            },
        )

    application_rows = _loan_application_rows(
        loan_seeds,
        customers,
        int(employee_id),
        int(product_id),
    )
    _execute_batches(
        connection,
        "INSERT INTO loan_applications (user_id, product_id, product_code, product_name, "
        "principal_amount, term_months, monthly_installment, status, created_at, reviewed_at, "
        "reviewed_by, approved_at) VALUES (:user_id, :product_id, :product_code, :product_name, "
        ":principal_amount, :term_months, :monthly_installment, :status, :created_at, "
        ":reviewed_at, :reviewed_by, :approved_at)",
        application_rows,
    )
    application_rows_by_user = {
        int(row["user_id"]): int(row["id"])
        for row in connection.execute(
            text("SELECT id, user_id FROM loan_applications WHERE user_id IN :user_ids").bindparams(
                bindparam("user_ids", expanding=True)
            ),
            {
                "user_ids": [
                    int(customers[loan_seed.customer_index]["id"]) for loan_seed in loan_seeds
                ]
            },
        ).mappings()
    }
    applications_by_customer_index = {
        loan_seed.customer_index: application_rows_by_user[
            int(customers[loan_seed.customer_index]["id"])
        ]
        for loan_seed in loan_seeds
    }

    _execute_batches(
        connection,
        "INSERT INTO loan_repayments (loan_application_id, installment_number, due_date, amount, "
        "status, processed_at, paid_at) VALUES (:loan_application_id, :installment_number, "
        ":due_date, :amount, :status, :processed_at, :paid_at)",
        _repayment_rows(loan_seeds, applications_by_customer_index),
    )

    ledger_entries = _base_ledger_entries(customers, account_ids, transfer_count)
    _execute_batches(
        connection,
        "INSERT INTO ledger_entries (posted_at, transaction_id, account_id, user_id, entry_type, "
        "amount) VALUES (:posted_at, :transaction_id, :account_id, :user_id, :entry_type, :amount)",
        ledger_entries,
    )
    _execute_batches(
        connection,
        "INSERT INTO ledger_entries (posted_at, transaction_id, account_id, user_id, entry_type, "
        "amount) VALUES (:posted_at, :transaction_id, :account_id, :user_id, :entry_type, :amount)",
        _loan_ledger_entries(loan_seeds, applications_by_customer_index, customers, account_ids),
    )

    balances = {
        index: balance - (fixed_account_balance if index == 0 else 0)
        for index, balance in planned_balances.items()
    }
    _execute_batches(
        connection,
        "UPDATE accounts SET balance = balance + :delta WHERE id = :account_id",
        ({"delta": delta, "account_id": account_ids[index]} for index, delta in balances.items()),
    )

    return _summary(
        already_present=False,
        customer_count=customer_count,
        account_count=customer_count,
        expected_transaction_counts=expected_transaction_counts,
        loan_seeds=loan_seeds,
    )
