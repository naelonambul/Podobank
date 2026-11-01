import calendar
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TypeVar

from sqlalchemy.engine import Engine

from podobank_api.features.loans import sql
from podobank_api.features.observability.events import record_financial_operation
from podobank_api.features.transactions import sql as transaction_sql
from podobank_api.features.transactions.service import MAX_BALANCE

logger = logging.getLogger(__name__)
Result = TypeVar("Result")


class LoanError(RuntimeError):
    reason = "loan_request_rejected"


class LoanProductNotFoundError(LoanError):
    reason = "product_not_found"


class LoanAccountNotFoundError(LoanError):
    reason = "account_not_found"


class ActiveLoanExistsError(LoanError):
    reason = "active_loan_exists"


class LoanApplicationNotFoundError(LoanError):
    reason = "application_not_found"


class LoanApplicationNotPendingError(LoanError):
    reason = "application_not_pending"


class LoanNotRepayingError(LoanError):
    reason = "loan_not_repaying"


class LoanInsufficientFundsError(LoanError):
    reason = "insufficient_funds"


class InvalidLoanAmountError(LoanError):
    reason = "invalid_amount"


class NoOverdueInstallmentsError(LoanError):
    reason = "no_overdue_installments"


class LoanBalanceLimitError(LoanError):
    reason = "balance_limit"


@dataclass(frozen=True)
class RepaymentRunResult:
    processed: int
    paid: int
    overdue: int
    skipped: int


@dataclass(frozen=True)
class ManualRepaymentResult:
    application_id: int
    status: str
    amount: int
    balance: int
    paid_installments: int


def utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def first_due_date(approved_at: datetime) -> date:
    """Return the first UTC month start on or after the clamped anniversary."""
    approval_date = approved_at.date()
    target_month = approval_date.month + 1
    target_year = approval_date.year
    if target_month == 13:
        target_month = 1
        target_year += 1
    target_day = min(approval_date.day, calendar.monthrange(target_year, target_month)[1])
    anniversary = date(target_year, target_month, target_day)
    first_of_target_month = date(target_year, target_month, 1)
    if first_of_target_month >= anniversary:
        return first_of_target_month
    if target_month == 12:
        return date(target_year + 1, 1, 1)
    return date(target_year, target_month + 1, 1)


def repayment_due_dates(approved_at: datetime, term_months: int) -> list[date]:
    first = first_due_date(approved_at)
    dates: list[date] = []
    for offset in range(term_months):
        month_index = first.year * 12 + first.month - 1 + offset
        year, zero_based_month = divmod(month_index, 12)
        dates.append(date(year, zero_based_month + 1, 1))
    return dates


class LoanService:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_products(self) -> list[dict[str, object]]:
        with self._engine.connect() as connection:
            return sql.list_products(connection)

    def apply(self, *, user_id: int, product_id: int) -> dict[str, object]:
        def perform() -> dict[str, object]:
            with self._engine.begin() as connection:
                # A user's account is the serialization lock for first-time applications.
                account = transaction_sql.lock_account_by_owner(connection, user_id)
                if account is None:
                    raise LoanAccountNotFoundError("customer account was not found")
                if sql.has_active_application(connection, user_id):
                    raise ActiveLoanExistsError("customer already has an active loan")
                product = sql.find_product(connection, product_id)
                if product is None:
                    raise LoanProductNotFoundError("loan product was not found")
                application_id = sql.insert_application(
                    connection,
                    user_id=user_id,
                    product=product,
                )
            with self._engine.connect() as connection:
                application = sql.find_application(connection, application_id)
            if application is None:
                raise RuntimeError("created loan application could not be read")
            return application

        return self._run("loan_application", perform)

    def customer_applications(self, *, user_id: int) -> list[dict[str, object]]:
        with self._engine.connect() as connection:
            applications = sql.list_customer_applications(connection, user_id=user_id)
            repayments = sql.list_repayments_for_applications(
                connection,
                application_ids=[int(row["id"]) for row in applications],
            )
        return [
            {**application, "repayments": repayments.get(int(application["id"]), [])}
            for application in applications
        ]

    def pending_applications(self, *, limit: int, offset: int) -> list[dict[str, object]]:
        with self._engine.connect() as connection:
            return sql.list_pending_applications(connection, limit=limit, offset=offset)

    def approve(self, *, application_id: int, employee_id: int) -> int:
        def perform() -> int:
            with self._engine.begin() as connection:
                application = sql.lock_application(connection, application_id)
                if application is None:
                    raise LoanApplicationNotFoundError("loan application was not found")
                if application["status"] != "pending":
                    raise LoanApplicationNotPendingError("loan application is not pending")

                reviewed_at = utc_now_naive()
                monthly_installment = int(application["monthly_installment"])
                due_dates = repayment_due_dates(reviewed_at, int(application["term_months"]))
                sql.insert_repayment_schedule(
                    connection,
                    application_id=application_id,
                    monthly_installment=monthly_installment,
                    due_dates=due_dates,
                )

                # Schedule rows are inserted after locking the loan, before the account lock.
                account = transaction_sql.lock_account_by_owner(
                    connection,
                    int(application["user_id"]),
                )
                if account is None:
                    raise LoanAccountNotFoundError("customer account was not found")
                principal = int(application["principal_amount"])
                balance = int(account["balance"])
                if balance + principal > MAX_BALANCE:
                    raise LoanBalanceLimitError("resulting balance exceeds the account limit")

                transaction_sql.add_balance(
                    connection,
                    account_id=int(account["id"]),
                    delta=principal,
                )
                transaction_sql.insert_ledger_entry(
                    connection,
                    posted_at=reviewed_at,
                    transaction_id=str(uuid.uuid4()),
                    account_id=int(account["id"]),
                    user_id=int(application["user_id"]),
                    entry_type="loan_disbursement",
                    amount=principal,
                )
                sql.update_application_review(
                    connection,
                    application_id=application_id,
                    status="repaying",
                    reviewed_by=employee_id,
                    reviewed_at=reviewed_at,
                    approved_at=reviewed_at,
                )
            return len(due_dates)

        return self._run("loan_approval", perform)

    def reject(self, *, application_id: int, employee_id: int) -> None:
        def perform() -> None:
            with self._engine.begin() as connection:
                application = sql.lock_application(connection, application_id)
                if application is None:
                    raise LoanApplicationNotFoundError("loan application was not found")
                if application["status"] != "pending":
                    raise LoanApplicationNotPendingError("loan application is not pending")
                reviewed_at = utc_now_naive()
                sql.update_application_review(
                    connection,
                    application_id=application_id,
                    status="rejected",
                    reviewed_by=employee_id,
                    reviewed_at=reviewed_at,
                    approved_at=None,
                )

        self._run("loan_rejection", perform)

    def process_due_repayments(self, *, as_of_date: date) -> RepaymentRunResult:
        def perform() -> RepaymentRunResult:
            with self._engine.connect() as connection:
                candidates = sql.due_repayment_candidates(connection, as_of_date)

            paid = 0
            overdue = 0
            skipped = 0
            processed_at = utc_now_naive()
            for repayment_id, application_id in candidates:
                outcome = self._process_candidate(
                    repayment_id=repayment_id,
                    application_id=application_id,
                    as_of_date=as_of_date,
                    processed_at=processed_at,
                )
                if outcome == "paid":
                    paid += 1
                elif outcome == "overdue":
                    overdue += 1
                else:
                    skipped += 1
            return RepaymentRunResult(
                processed=paid + overdue,
                paid=paid,
                overdue=overdue,
                skipped=skipped,
            )

        return self._run("repayment_batch", perform)

    def _process_candidate(
        self,
        *,
        repayment_id: int,
        application_id: int,
        as_of_date: date,
        processed_at: datetime,
    ) -> str:
        with self._engine.begin() as connection:
            # All three row types use the shared lock order: loan, repayment, account.
            application = sql.lock_application(connection, application_id)
            if application is None or application["status"] != "repaying":
                return "skipped"
            repayment = sql.lock_repayment(
                connection,
                repayment_id=repayment_id,
                application_id=application_id,
            )
            due_date = repayment["due_date"] if repayment is not None else None
            if isinstance(due_date, datetime):
                due_date = due_date.date()
            if (
                repayment is None
                or repayment["status"] != "scheduled"
                or due_date is None
                or due_date > as_of_date
            ):
                return "skipped"

            account = transaction_sql.lock_account_by_owner(
                connection,
                int(application["user_id"]),
            )
            if account is None:
                raise LoanAccountNotFoundError("customer account was not found")
            amount = int(repayment["amount"])
            balance = int(account["balance"])
            if balance < amount:
                sql.update_repayment_status(
                    connection,
                    repayment_id=repayment_id,
                    expected_status="scheduled",
                    new_status="overdue",
                    processed_at=processed_at,
                    paid_at=None,
                )
                return "overdue"

            transaction_sql.add_balance(
                connection,
                account_id=int(account["id"]),
                delta=-amount,
            )
            transaction_sql.insert_ledger_entry(
                connection,
                posted_at=processed_at,
                transaction_id=str(uuid.uuid4()),
                account_id=int(account["id"]),
                user_id=int(application["user_id"]),
                entry_type="loan_repayment",
                amount=-amount,
            )
            sql.update_repayment_status(
                connection,
                repayment_id=repayment_id,
                expected_status="scheduled",
                new_status="paid",
                processed_at=processed_at,
                paid_at=processed_at,
            )
            if not sql.has_open_repayments(connection, application_id):
                sql.mark_application_repaid(connection, application_id)
            return "paid"

    def repay_overdue(
        self,
        *,
        user_id: int,
        application_id: int,
        amount: int,
    ) -> ManualRepaymentResult:
        def perform() -> ManualRepaymentResult:
            if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
                raise InvalidLoanAmountError("repayment amount must be a positive integer")
            with self._engine.begin() as connection:
                application = sql.lock_application(connection, application_id)
                if application is None or int(application["user_id"]) != user_id:
                    raise LoanApplicationNotFoundError("loan application was not found")
                if application["status"] != "repaying":
                    raise LoanNotRepayingError("loan is not accepting repayments")
                overdue_rows = sql.lock_overdue_repayments(
                    connection,
                    application_id=application_id,
                )
                if not overdue_rows:
                    raise NoOverdueInstallmentsError("loan has no overdue installments")

                installment_amount = int(application["monthly_installment"])
                overdue_count = len(overdue_rows)
                if amount % installment_amount != 0 or amount > installment_amount * overdue_count:
                    raise InvalidLoanAmountError(
                        "repayment must cover whole overdue installments without overpayment"
                    )
                paid_installments = amount // installment_amount
                account = transaction_sql.lock_account_by_owner(connection, user_id)
                if account is None:
                    raise LoanAccountNotFoundError("customer account was not found")
                balance = int(account["balance"])
                if balance < amount:
                    raise LoanInsufficientFundsError("account balance is insufficient")

                processed_at = utc_now_naive()
                for repayment in overdue_rows[:paid_installments]:
                    sql.update_repayment_status(
                        connection,
                        repayment_id=int(repayment["id"]),
                        expected_status="overdue",
                        new_status="paid",
                        processed_at=processed_at,
                        paid_at=processed_at,
                    )
                transaction_sql.add_balance(
                    connection,
                    account_id=int(account["id"]),
                    delta=-amount,
                )
                transaction_sql.insert_ledger_entry(
                    connection,
                    posted_at=processed_at,
                    transaction_id=str(uuid.uuid4()),
                    account_id=int(account["id"]),
                    user_id=user_id,
                    entry_type="loan_repayment",
                    amount=-amount,
                )
                has_open = sql.has_open_repayments(connection, application_id)
                if not has_open:
                    sql.mark_application_repaid(connection, application_id)
                return ManualRepaymentResult(
                    application_id=application_id,
                    status="repaying" if has_open else "repaid",
                    amount=amount,
                    balance=balance - amount,
                    paid_installments=paid_installments,
                )

        return self._run("manual_loan_repayment", perform)

    @staticmethod
    def _run(operation: str, action: Callable[[], Result]) -> Result:
        try:
            result = action()
        except LoanError as error:
            record_financial_operation(operation, "failure", error.reason)
            logger.info(
                "financial_operation operation=%s outcome=failure reason=%s",
                operation,
                error.reason,
            )
            raise
        except Exception:
            record_financial_operation(operation, "failure", "database_error")
            logger.info(
                "financial_operation operation=%s outcome=failure reason=database_error",
                operation,
            )
            raise
        repayment_counts = None
        if operation == "repayment_batch" and isinstance(result, RepaymentRunResult):
            repayment_counts = (
                result.processed,
                result.paid,
                result.overdue,
                result.skipped,
            )
        record_financial_operation(
            operation,
            "success",
            "completed",
            repayment_counts=repayment_counts,
        )
        logger.info(
            "financial_operation operation=%s outcome=success reason=completed",
            operation,
        )
        return result
