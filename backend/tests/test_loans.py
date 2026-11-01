import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from datetime import date, datetime
from io import StringIO
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import text

from podobank_api.app import create_app
from podobank_api.cli import main as cli_main
from podobank_api.database import create_database_engine, reset_database, validate_reset_target
from podobank_api.features.auth.tokens import SESSION_COOKIE_NAME, issue_session_token
from podobank_api.features.loans.service import (
    ActiveLoanExistsError,
    LoanService,
    first_due_date,
    repayment_due_dates,
)
from podobank_api.features.transactions.service import TransactionService
from podobank_api.settings import Settings

TEST_EMPLOYEE_PHONE = "01000000009"
TEST_EMPLOYEE_PASSWORD = "test-employee-password"
CUSTOMER_PHONE = "01022220001"
OTHER_CUSTOMER_PHONE = "01022220002"
CUSTOMER_ACCOUNT_NUMBER = "100000000201"
OTHER_ACCOUNT_NUMBER = "100000000202"
APPROVAL_TIME = datetime(2026, 10, 31, 12, 30)


class LoanApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_url = os.environ.get("DATABASE_URL", "")
        if not self.database_url:
            self.fail("DATABASE_URL must point to the isolated podobank_test database")
        validate_reset_target("test", self.database_url)
        self.engine = create_database_engine(self.database_url)
        reset_database(
            self.engine,
            app_env="test",
            employee_phone=TEST_EMPLOYEE_PHONE,
            employee_password=TEST_EMPLOYEE_PASSWORD,
        )
        self.settings = Settings.from_environment(
            {
                "APP_ENV": "test",
                "DATABASE_URL": self.database_url,
                "KAKAO_REST_API_KEY": "test-rest-api-key",
                "KAKAO_CLIENT_SECRET": "test-client-secret",
                "KAKAO_REDIRECT_URI": "http://localhost:5173/auth/kakao/callback",
                "JWT_SECRET": "test-only-secret-with-more-than-32-characters",
                "JWT_LIFETIME_MINUTES": "120",
                "AUTH_COOKIE_SECURE": "false",
                "FRONTEND_ORIGINS": "http://localhost:5173,http://localhost:8080",
                "BANK_EMPLOYEE_PHONE": TEST_EMPLOYEE_PHONE,
                "BANK_EMPLOYEE_PASSWORD": TEST_EMPLOYEE_PASSWORD,
            }
        )
        with self.engine.begin() as connection:
            self.customer_id = self._insert_customer(
                connection,
                "대출 고객",
                CUSTOMER_PHONE,
                CUSTOMER_ACCOUNT_NUMBER,
            )
            self.other_customer_id = self._insert_customer(
                connection,
                "다른 고객",
                OTHER_CUSTOMER_PHONE,
                OTHER_ACCOUNT_NUMBER,
            )
            self.employee_id = int(
                connection.execute(
                    text("SELECT id FROM users WHERE phone_number = :phone"),
                    {"phone": TEST_EMPLOYEE_PHONE},
                ).scalar_one()
            )
            self.product_id = int(
                connection.execute(
                    text(
                        "INSERT INTO loan_products "
                        "(code, name, principal_amount, term_months, monthly_installment) "
                        "VALUES ('test_short', '테스트 단기 대출', 2000, 2, 1000)"
                    )
                ).lastrowid
            )
        self.app = create_app(self.settings, engine=self.engine)
        self.client = TestClient(self.app)
        self.transaction_service = TransactionService(self.engine)
        self.loan_service = LoanService(self.engine)

    def tearDown(self) -> None:
        self.client.close()
        self.engine.dispose()

    @staticmethod
    def _insert_customer(connection, name: str, phone: str, account_number: str) -> int:
        user_id = connection.execute(
            text(
                "INSERT INTO users (name, phone_number, age, gender, marital_status, "
                "is_employed, role) VALUES (:name, :phone, 30, 'female', 'single', 1, 'customer')"
            ),
            {"name": name, "phone": phone},
        ).lastrowid
        connection.execute(
            text(
                "INSERT INTO accounts (owner_user_id, account_number, balance) "
                "VALUES (:user_id, :account_number, 0)"
            ),
            {"user_id": user_id, "account_number": account_number},
        )
        return int(user_id)

    def _client_as(self, user_id: int) -> TestClient:
        self.client.cookies.set(
            SESSION_COOKIE_NAME,
            issue_session_token(user_id, self.settings),
        )
        return self.client

    def _account_id(self, user_id: int | None = None) -> int:
        with self.engine.connect() as connection:
            account_id = connection.execute(
                text("SELECT id FROM accounts WHERE owner_user_id = :user_id"),
                {"user_id": user_id or self.customer_id},
            ).scalar_one()
        return int(account_id)

    def _balance(self, user_id: int | None = None) -> int:
        with self.engine.connect() as connection:
            balance = connection.execute(
                text("SELECT balance FROM accounts WHERE owner_user_id = :user_id"),
                {"user_id": user_id or self.customer_id},
            ).scalar_one()
        return int(balance)

    def _application_id(self, response) -> int:
        self.assertEqual(response.status_code, 201, response.text)
        return int(response.json()["id"])

    def _apply(self, user_id: int | None = None, product_id: int | None = None) -> int:
        response = self._client_as(user_id or self.customer_id).post(
            "/loans/applications",
            json={"product_id": product_id or self.product_id},
        )
        return self._application_id(response)

    def _approve(self, application_id: int) -> object:
        with patch(
            "podobank_api.features.loans.service.utc_now_naive",
            return_value=APPROVAL_TIME,
        ):
            return self._client_as(self.employee_id).post(f"/loans/{application_id}/approve")

    def _repayments(self, application_id: int) -> list[dict[str, object]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT installment_number, due_date, amount, status "
                    "FROM loan_repayments WHERE loan_application_id = :application_id "
                    "ORDER BY installment_number"
                ),
                {"application_id": application_id},
            ).mappings()
            return [dict(row) for row in rows]

    def _ledger(self, entry_type: str | None = None) -> list[dict[str, object]]:
        where = " WHERE user_id = :user_id"
        parameters: dict[str, object] = {"user_id": self.customer_id}
        if entry_type is not None:
            where += " AND entry_type = :entry_type"
            parameters["entry_type"] = entry_type
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT entry_type, amount FROM ledger_entries"
                    f"{where} ORDER BY posted_at, entry_id"
                ),
                parameters,
            ).mappings()
            return [dict(row) for row in rows]

    def test_first_due_date_clamps_anniversary_then_uses_month_start(self) -> None:
        self.assertEqual(first_due_date(datetime(2026, 1, 1)), date(2026, 2, 1))
        self.assertEqual(first_due_date(datetime(2026, 1, 31)), date(2026, 3, 1))
        self.assertEqual(first_due_date(datetime(2026, 3, 30)), date(2026, 5, 1))
        self.assertEqual(first_due_date(datetime(2026, 12, 31)), date(2027, 2, 1))
        schedule = repayment_due_dates(APPROVAL_TIME, 60)
        self.assertEqual(len(schedule), 60)
        self.assertEqual(schedule[:3], [date(2026, 12, 1), date(2027, 1, 1), date(2027, 2, 1)])
        self.assertEqual(schedule[-1], date(2031, 11, 1))

    def test_product_listing_application_snapshot_active_rule_and_rejection(self) -> None:
        unauthenticated = TestClient(self.app).get("/loans/products")
        self.assertEqual(unauthenticated.status_code, 401)
        products = self._client_as(self.customer_id).get("/loans/products")
        self.assertEqual(products.status_code, 200)
        seeded = {item["code"]: item for item in products.json()["items"]}
        self.assertEqual(seeded["car_purchase"]["principal_amount"], 30_000_000)
        self.assertEqual(seeded["car_purchase"]["term_months"], 60)
        self.assertEqual(seeded["car_purchase"]["monthly_installment"], 500_000)

        application_id = self._apply()
        pending = self._client_as(self.customer_id).get("/loans/me").json()["items"][0]
        self.assertEqual(pending["id"], application_id)
        self.assertEqual(pending["principal_amount"], 2_000)
        self.assertEqual(pending["term_months"], 2)
        self.assertEqual(pending["monthly_installment"], 1_000)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE loan_products SET name = '변경 상품', principal_amount = 4000, "
                    "monthly_installment = 2000 WHERE id = :product_id"
                ),
                {"product_id": self.product_id},
            )
        duplicate = self._client_as(self.customer_id).post(
            "/loans/applications",
            json={"product_id": self.product_id},
        )
        self.assertEqual(duplicate.status_code, 409)

        employee_client = self._client_as(self.employee_id)
        pending_list = employee_client.get("/loans/pending")
        self.assertEqual(pending_list.status_code, 200)
        self.assertEqual(pending_list.json()["items"][0]["id"], application_id)
        rejected = employee_client.post(f"/loans/{application_id}/reject")
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.json()["status"], "rejected")
        self.assertGreater(self._apply(), application_id)

    def test_employee_approval_is_atomic_and_creates_full_schedule(self) -> None:
        application_id = self._apply()
        approval = self._approve(application_id)
        self.assertEqual(approval.status_code, 200, approval.text)
        self.assertEqual(approval.json()["repayment_count"], 2)
        self.assertEqual(self._balance(), 2_000)
        active_duplicate = self._client_as(self.customer_id).post(
            "/loans/applications",
            json={"product_id": self.product_id},
        )
        self.assertEqual(active_duplicate.status_code, 409)
        schedule = self._repayments(application_id)
        self.assertEqual([row["status"] for row in schedule], ["scheduled", "scheduled"])
        self.assertEqual([row["amount"] for row in schedule], [1_000, 1_000])
        self.assertEqual(
            [
                row["due_date"].date() if isinstance(row["due_date"], datetime) else row["due_date"]
                for row in schedule
            ],
            [date(2026, 12, 1), date(2027, 1, 1)],
        )
        self.assertEqual(
            self._ledger("loan_disbursement"),
            [{"entry_type": "loan_disbursement", "amount": 2_000}],
        )

    def test_approved_home_loan_persists_all_360_monthly_installments(self) -> None:
        with self.engine.connect() as connection:
            product_id = int(
                connection.execute(
                    text("SELECT id FROM loan_products WHERE code = 'home_purchase'")
                ).scalar_one()
            )
        application_id = self._apply(product_id=product_id)
        approval = self._approve(application_id)

        self.assertEqual(approval.status_code, 200, approval.text)
        self.assertEqual(approval.json()["repayment_count"], 360)
        schedule = self._repayments(application_id)
        self.assertEqual(len(schedule), 360)
        self.assertEqual({row["amount"] for row in schedule}, {1_000_000})
        self.assertEqual(schedule[0]["installment_number"], 1)
        self.assertEqual(schedule[-1]["installment_number"], 360)

    def test_failed_disbursement_rolls_back_balance_schedule_ledger_and_review(self) -> None:
        application_id = self._apply()
        with patch(
            "podobank_api.features.loans.service.transaction_sql.insert_ledger_entry",
            side_effect=RuntimeError("forced ledger failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.loan_service.approve(
                    application_id=application_id,
                    employee_id=self.employee_id,
                )

        self.assertEqual(self._balance(), 0)
        self.assertEqual(self._repayments(application_id), [])
        self.assertEqual(self._ledger(), [])
        with self.engine.connect() as connection:
            status_value = connection.execute(
                text("SELECT status FROM loan_applications WHERE id = :application_id"),
                {"application_id": application_id},
            ).scalar_one()
        self.assertEqual(status_value, "pending")

    def test_daily_processing_catches_up_oldest_first_without_partial_debit(self) -> None:
        application_id = self._apply()
        self.assertEqual(self._approve(application_id).status_code, 200)
        self.transaction_service.withdraw(user_id=self.customer_id, amount=2_000)

        result = self.loan_service.process_due_repayments(as_of_date=date(2027, 1, 1))
        self.assertEqual(
            (result.processed, result.paid, result.overdue, result.skipped),
            (2, 0, 2, 0),
        )
        self.assertEqual(self._balance(), 0)
        self.assertEqual(
            [row["status"] for row in self._repayments(application_id)],
            ["overdue", "overdue"],
        )
        self.assertEqual(self._ledger("loan_repayment"), [])
        repeated = self.loan_service.process_due_repayments(as_of_date=date(2027, 1, 1))
        self.assertEqual((repeated.processed, repeated.paid, repeated.overdue), (0, 0, 0))

    def test_failed_automatic_ledger_write_rolls_back_debit_and_schedule_state(self) -> None:
        application_id = self._apply()
        self.assertEqual(self._approve(application_id).status_code, 200)
        with patch(
            "podobank_api.features.loans.service.transaction_sql.insert_ledger_entry",
            side_effect=RuntimeError("forced ledger failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.loan_service.process_due_repayments(as_of_date=date(2026, 12, 1))

        self.assertEqual(self._balance(), 2_000)
        self.assertEqual(self._repayments(application_id)[0]["status"], "scheduled")
        self.assertEqual(self._ledger("loan_repayment"), [])
        retry = self.loan_service.process_due_repayments(as_of_date=date(2026, 12, 1))
        self.assertEqual(retry.paid, 1)
        self.assertEqual(self._balance(), 1_000)

    def test_missed_installments_are_processed_in_order_and_debit_once(self) -> None:
        application_id = self._apply()
        self.assertEqual(self._approve(application_id).status_code, 200)
        self.transaction_service.withdraw(user_id=self.customer_id, amount=500)

        with ThreadPoolExecutor(max_workers=2) as executor:
            runs = list(
                executor.map(
                    lambda _index: self.loan_service.process_due_repayments(
                        as_of_date=date(2027, 1, 1)
                    ),
                    range(2),
                )
            )
        self.assertEqual(sum(run.paid for run in runs), 1)
        self.assertEqual(sum(run.overdue for run in runs), 1)
        self.assertEqual(self._balance(), 500)
        self.assertEqual(
            [row["status"] for row in self._repayments(application_id)],
            ["paid", "overdue"],
        )
        self.assertEqual(
            self._ledger("loan_repayment"),
            [{"entry_type": "loan_repayment", "amount": -1_000}],
        )

    def test_concurrent_applications_create_only_one_active_loan(self) -> None:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    self.loan_service.apply,
                    user_id=self.customer_id,
                    product_id=self.product_id,
                )
                for _ in range(2)
            ]
        successes = 0
        active_loan_errors = 0
        for future in futures:
            try:
                future.result()
                successes += 1
            except ActiveLoanExistsError:
                active_loan_errors += 1
        self.assertEqual((successes, active_loan_errors), (1, 1))
        with self.engine.connect() as connection:
            active_count = connection.execute(
                text(
                    "SELECT COUNT(*) FROM loan_applications WHERE user_id = :user_id "
                    "AND status IN ('pending', 'repaying')"
                ),
                {"user_id": self.customer_id},
            ).scalar_one()
        self.assertEqual(active_count, 1)

    def test_daily_cli_runs_once_and_same_date_retry_is_safe(self) -> None:
        application_id = self._apply()
        self.assertEqual(self._approve(application_id).status_code, 200)

        first_output = StringIO()
        with redirect_stdout(first_output):
            first_exit = cli_main(["process-repayments", "--as-of-date", "2026-12-01"])
        second_output = StringIO()
        with redirect_stdout(second_output):
            second_exit = cli_main(["process-repayments", "--as-of-date", "2026-12-01"])

        self.assertEqual(first_exit, 0)
        self.assertIn("processed=1 paid=1 overdue=0 skipped=0", first_output.getvalue())
        self.assertEqual(second_exit, 0)
        self.assertIn("processed=0 paid=0 overdue=0 skipped=0", second_output.getvalue())
        self.assertEqual(self._balance(), 1_000)
        self.assertEqual(
            self._ledger("loan_repayment"),
            [{"entry_type": "loan_repayment", "amount": -1_000}],
        )

    def test_manual_repayment_is_owner_scoped_whole_installments_and_oldest_first(self) -> None:
        application_id = self._apply()
        self.assertEqual(self._approve(application_id).status_code, 200)
        self.transaction_service.withdraw(user_id=self.customer_id, amount=2_000)
        run = self.loan_service.process_due_repayments(as_of_date=date(2027, 1, 1))
        self.assertEqual(run.overdue, 2)

        customer_client = self._client_as(self.customer_id)
        partial = customer_client.post(
            f"/loans/me/{application_id}/repayments", json={"amount": 500}
        )
        overpayment = customer_client.post(
            f"/loans/me/{application_id}/repayments", json={"amount": 3_000}
        )
        insufficient = customer_client.post(
            f"/loans/me/{application_id}/repayments", json={"amount": 1_000}
        )
        wrong_owner = self._client_as(self.other_customer_id).post(
            f"/loans/me/{application_id}/repayments", json={"amount": 1_000}
        )
        self.assertEqual(partial.status_code, 422)
        self.assertEqual(overpayment.status_code, 422)
        self.assertEqual(insufficient.status_code, 409)
        self.assertEqual(wrong_owner.status_code, 404)
        self.assertEqual(self._balance(), 0)
        self.assertEqual(
            [row["status"] for row in self._repayments(application_id)],
            ["overdue", "overdue"],
        )

        self.transaction_service.deposit(user_id=self.customer_id, amount=2_500)
        retry = self.loan_service.process_due_repayments(as_of_date=date(2027, 1, 1))
        self.assertEqual(retry.processed, 0)
        self.assertEqual(self._balance(), 2_500)
        paid = self._client_as(self.customer_id).post(
            f"/loans/me/{application_id}/repayments", json={"amount": 2_000}
        )
        self.assertEqual(paid.status_code, 200, paid.text)
        self.assertEqual(paid.json()["status"], "repaid")
        self.assertEqual(paid.json()["paid_installments"], 2)
        self.assertEqual(self._balance(), 500)
        self.assertEqual(
            [row["status"] for row in self._repayments(application_id)],
            ["paid", "paid"],
        )
        self.assertEqual(
            self._ledger("loan_repayment"),
            [{"entry_type": "loan_repayment", "amount": -2_000}],
        )
        self.assertGreater(self._apply(), application_id)

    def test_only_customers_apply_and_only_employees_review(self) -> None:
        application_id = self._apply()
        self.assertEqual(
            self._client_as(self.customer_id).get("/loans/pending").status_code,
            403,
        )
        self.assertEqual(
            self._client_as(self.customer_id).post(f"/loans/{application_id}/approve").status_code,
            403,
        )
        self.assertEqual(
            self._client_as(self.employee_id).get("/loans/products").status_code,
            403,
        )
        approved = self._approve(application_id)
        self.assertEqual(approved.status_code, 200)

    def test_financial_logs_do_not_include_customer_or_amount(self) -> None:
        with self.assertLogs("podobank_api.features.loans.service", level="INFO") as captured:
            self._apply()
        rendered = " ".join(captured.output)
        self.assertNotIn(CUSTOMER_PHONE, rendered)
        self.assertNotIn(CUSTOMER_ACCOUNT_NUMBER, rendered)
        self.assertNotIn("2000", rendered)


if __name__ == "__main__":
    unittest.main()
