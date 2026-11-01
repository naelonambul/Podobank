import calendar
from datetime import UTC, date, datetime

from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from podobank_api.features.accounts.service import (
    account_by_user_id,
    credit_user_account,
    debit_user_account,
)
from podobank_api.features.loans import sql
from podobank_api.features.transactions.service import record_internal_entry


class LoanError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _first_of_next_month(value: date) -> date:
    year, month = value.year, value.month + 1
    if month == 13:
        year += 1
        month = 1
    return date(year, month, 1)


def _add_one_month(value: date) -> date:
    year, month = value.year, value.month + 1
    if month == 13:
        year += 1
        month = 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def first_due_date(approved_at: datetime) -> date:
    approval_date = approved_at.date()
    due_date = _first_of_next_month(approval_date)
    one_month_later = _add_one_month(approval_date)
    if due_date < one_month_later:
        due_date = _first_of_next_month(due_date)
    return due_date


def _monthly_due_dates(first_due: date, term_months: int) -> list[str]:
    dates = []
    for index in range(term_months):
        month_index = first_due.year * 12 + first_due.month - 1 + index
        year, month_zero = divmod(month_index, 12)
        dates.append(date(year, month_zero + 1, 1).isoformat())
    return dates


def loan_products(engine: Engine) -> list[dict[str, object]]:
    with engine.connect() as connection:
        return sql.list_products(connection)


def apply_for_loan(engine: Engine, user_id: int, product_id: int) -> int:
    try:
        with engine.begin() as connection:
            product = sql.product_by_id(connection, product_id)
            if product is None:
                raise LoanError(404, "loan product not found")
            if sql.active_loan_for_user(connection, user_id):
                raise LoanError(409, "an active loan application already exists")
            return sql.insert_loan_application(connection, user_id, product_id)
    except IntegrityError as error:
        raise LoanError(409, "an active loan application already exists") from error


def _attach_installments(connection, loan: dict[str, object]) -> dict[str, object]:
    result = dict(loan)
    result["installments"] = sql.list_installments(connection, int(loan["id"]))
    return result


def user_loans(engine: Engine, user_id: int) -> list[dict[str, object]]:
    with engine.connect() as connection:
        rows = sql.list_user_loans(connection, user_id)
        return [_attach_installments(connection, row) for row in rows]


def staff_pending_applications(
    engine: Engine,
    query: str | None,
    limit: int,
) -> list[dict[str, object]]:
    with engine.connect() as connection:
        return sql.list_pending_applications(connection, query=query, limit=limit)


def decide_application(
    engine: Engine,
    loan_id: int,
    *,
    decision: str,
    now: datetime | None = None,
) -> dict[str, object]:
    if decision not in {"approve", "reject"}:
        raise LoanError(422, "decision must be approve or reject")
    decision_time = now or _now()
    decision_stamp = _iso(decision_time)
    with engine.begin() as connection:
        application = sql.pending_application_for_staff(connection, loan_id)
        if application is None:
            raise LoanError(404, "pending loan application not found")
        product = sql.product_by_id(connection, int(application["product_id"]))
        if product is None:
            raise LoanError(409, "loan product is no longer available")

        approved_at = decision_stamp if decision == "approve" else None
        next_status = "repaying" if decision == "approve" else "rejected"
        if not sql.set_decision(
            connection,
            loan_id,
            decision=next_status,
            decided_at=decision_stamp,
            approved_at=approved_at,
        ):
            raise LoanError(409, "loan application was already decided")

        if decision == "approve":
            term_months = int(product["term_months"])
            monthly_amount = int(product["monthly_installment_krw"])
            principal = int(product["principal_krw"])
            if principal % term_months:
                raise LoanError(409, "loan product amount must divide evenly by its term")
            due_dates = _monthly_due_dates(first_due_date(decision_time), term_months)
            sql.insert_installments(
                connection,
                loan_id,
                [(index + 1, due, monthly_amount) for index, due in enumerate(due_dates)],
            )
            account = account_by_user_id(connection, int(application["user_id"]))
            if account is None:
                raise LoanError(409, "applicant account not found")
            credit_user_account(connection, int(application["user_id"]), principal)
            record_internal_entry(
                connection,
                account_id=int(account["id"]),
                entry_type="loan_disbursement",
                amount_krw=principal,
                memo=str(product["name"]),
            )
    return {"loan_id": loan_id, "status": next_status}


def _set_loan_paid_if_complete(connection, loan_id: int) -> None:
    if not sql.has_unpaid_installments(connection, loan_id):
        sql.mark_loan_paid_off(connection, loan_id)


def process_due_repayments(engine: Engine, as_of: date | None = None) -> dict[str, int]:
    due_date = (as_of or date.today()).isoformat()
    with engine.connect() as connection:
        installment_ids = sql.due_installment_ids(connection, due_date)

    paid_count = 0
    overdue_count = 0
    for installment_id in installment_ids:
        with engine.begin() as connection:
            installment = sql.claim_due_installment(connection, installment_id, due_date)
            if installment is None:
                continue
            amount = int(installment["amount_krw"])
            user_id = int(installment["user_id"])
            balance = debit_user_account(connection, user_id, amount)
            if balance is None:
                sql.finish_installment(
                    connection,
                    installment_id,
                    status="overdue",
                    paid_at=None,
                )
                overdue_count += 1
                continue

            paid_at = _iso(_now())
            sql.finish_installment(
                connection,
                installment_id,
                status="paid",
                paid_at=paid_at,
            )
            account = account_by_user_id(connection, user_id)
            if account is None:
                raise LoanError(409, "account not found")
            record_internal_entry(
                connection,
                account_id=int(account["id"]),
                entry_type="loan_repayment",
                amount_krw=amount,
                memo=f"loan installment {installment['installment_number']}",
            )
            _set_loan_paid_if_complete(connection, int(installment["loan_id"]))
            paid_count += 1
    return {"paid": paid_count, "overdue": overdue_count}


def repay_overdue(
    engine: Engine,
    user_id: int,
    loan_id: int,
    amount_krw: int,
) -> dict[str, object]:
    with engine.begin() as connection:
        loan = sql.loan_for_user(connection, loan_id, user_id)
        if loan is None or loan["status"] != "repaying":
            raise LoanError(404, "active loan not found")
        monthly_amount = int(loan["monthly_installment_krw"])
        if amount_krw % monthly_amount:
            raise LoanError(422, "repayment must be a whole number of monthly installments")
        overdue = sql.overdue_installments(connection, loan_id)
        selected: list[dict[str, object]] = []
        selected_amount = 0
        for installment in overdue:
            if selected_amount >= amount_krw:
                break
            selected.append(installment)
            selected_amount += int(installment["amount_krw"])
        if selected_amount != amount_krw:
            raise LoanError(422, "repayment may only cover existing overdue installments")
        if not selected:
            raise LoanError(409, "no overdue installments to repay")
        installment_ids = [int(item["id"]) for item in selected]
        if not sql.claim_overdue_installments(connection, installment_ids):
            raise LoanError(409, "overdue installments changed; retry the repayment")

        balance = debit_user_account(connection, user_id, amount_krw)
        if balance is None:
            raise LoanError(409, "insufficient funds")
        paid_at = _iso(_now())
        for installment_id in installment_ids:
            sql.finish_installment(
                connection,
                installment_id,
                status="paid",
                paid_at=paid_at,
            )
        account = account_by_user_id(connection, user_id)
        if account is None:
            raise LoanError(409, "account not found")
        record_internal_entry(
            connection,
            account_id=int(account["id"]),
            entry_type="loan_repayment",
            amount_krw=amount_krw,
            memo=f"loan {loan_id} overdue repayment",
        )
        _set_loan_paid_if_complete(connection, loan_id)
    return {"loan_id": loan_id, "amount_krw": amount_krw, "balance_krw": balance}
