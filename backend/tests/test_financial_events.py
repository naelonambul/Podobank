import os
import unittest
import uuid
from datetime import date
from unittest.mock import patch

from sqlalchemy import text

from podobank_api.database import create_database_engine, initialize_database
from podobank_api.features.financial_events import mongodb
from podobank_api.features.loans.service import LoanService
from podobank_api.features.transactions.service import InsufficientFundsError, TransactionService

TEST_EMPLOYEE_PHONE = "01000000009"
TEST_EMPLOYEE_PASSWORD = "test-employee-password"


class MongoEventWriterConfigurationTests(unittest.TestCase):
    def test_client_disables_driver_write_retries(self) -> None:
        mongodb.close_mongodb_clients()
        self.addCleanup(mongodb.close_mongodb_clients)

        with patch("podobank_api.features.financial_events.mongodb.MongoClient") as client:
            mongodb._client_for("mongodb://mongo:27017")

        client.assert_called_once_with(
            "mongodb://mongo:27017",
            connectTimeoutMS=1_000,
            serverSelectionTimeoutMS=mongodb.MONGODB_TIMEOUT_MS,
            timeoutMS=mongodb.MONGODB_TIMEOUT_MS,
            retryWrites=False,
        )


class FinancialEventDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_url = os.environ.get("DATABASE_URL", "")
        if not self.database_url:
            self.fail("DATABASE_URL must point to the isolated podobank_test database")
        if os.environ.get("APP_ENV") != "test":
            self.fail("APP_ENV=test is required for financial event verification")
        self.engine = create_database_engine(self.database_url)
        initialize_database(
            self.engine,
            employee_phone=TEST_EMPLOYEE_PHONE,
            employee_password=TEST_EMPLOYEE_PASSWORD,
        )

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_database_schema_does_not_create_an_event_outbox(self) -> None:
        with self.engine.connect() as connection:
            outbox_exists = connection.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = DATABASE() AND table_name = 'financial_event_outbox'"
                )
            ).first()

        self.assertIsNone(outbox_exists)

    def test_deposit_writes_safe_event_after_mariadb_commit(self) -> None:
        user_id, account_id = self._create_customer()
        captured: list[dict[str, object]] = []

        def capture_after_commit(event: dict[str, object]) -> None:
            with self.engine.connect() as connection:
                balance = connection.execute(
                    text("SELECT balance FROM accounts WHERE id = :account_id"),
                    {"account_id": account_id},
                ).scalar_one()
                ledger_count = connection.execute(
                    text("SELECT COUNT(*) FROM ledger_entries WHERE account_id = :account_id"),
                    {"account_id": account_id},
                ).scalar_one()
            self.assertEqual(balance, 5)
            self.assertEqual(ledger_count, 1)
            captured.append(event)

        with patch(
            "podobank_api.features.transactions.service.write_event_best_effort",
            side_effect=capture_after_commit,
            create=True,
        ) as write_event:
            result = TransactionService(self.engine).deposit(user_id=user_id, amount=5)

        write_event.assert_called_once()
        self.assertEqual(result.balance, 5)
        event = captured[0]
        self.assertEqual(
            set(event),
            {
                "event_id",
                "schema_version",
                "timestamp",
                "event",
                "operation",
                "outcome",
                "reason",
            },
        )
        self.assertEqual(event["event"], "financial_operation")
        self.assertEqual(event["operation"], "deposit")
        self.assertEqual(event["outcome"], "success")
        self.assertEqual(event["reason"], "completed")
        self.assertEqual(event["schema_version"], 1)
        uuid.UUID(str(event["event_id"]))

    def test_mongodb_write_failure_does_not_fail_or_rollback_deposit(self) -> None:
        user_id, account_id = self._create_customer()

        with patch(
            "podobank_api.features.transactions.service.write_event_best_effort",
            side_effect=RuntimeError("MongoDB is unavailable"),
            create=True,
        ) as write_event:
            result = TransactionService(self.engine).deposit(user_id=user_id, amount=7)

        write_event.assert_called_once()
        self.assertEqual(result.balance, 7)
        with self.engine.connect() as connection:
            balance = connection.execute(
                text("SELECT balance FROM accounts WHERE id = :account_id"),
                {"account_id": account_id},
            ).scalar_one()
        self.assertEqual(balance, 7)

    def test_failed_withdrawal_does_not_write_mongodb_event(self) -> None:
        user_id, _account_id = self._create_customer()

        with patch(
            "podobank_api.features.transactions.service.write_event_best_effort",
            create=True,
        ) as write_event:
            with self.assertRaises(InsufficientFundsError):
                TransactionService(self.engine).withdraw(user_id=user_id, amount=1)

        write_event.assert_not_called()

    def test_repayment_batch_writes_one_event_per_committed_candidate(self) -> None:
        user_id, account_id = self._create_customer()
        product_id = self._create_product()
        service = LoanService(self.engine)
        with patch(
            "podobank_api.features.loans.service.write_event_best_effort",
            create=True,
        ) as write_event:
            application = service.apply(user_id=user_id, product_id=product_id)
            with self.engine.connect() as connection:
                employee_id = int(
                    connection.execute(
                        text("SELECT id FROM users WHERE phone_number = :phone"),
                        {"phone": TEST_EMPLOYEE_PHONE},
                    ).scalar_one()
                )
            service.approve(application_id=int(application["id"]), employee_id=employee_id)

        with self.engine.begin() as connection:
            connection.execute(
                text("UPDATE accounts SET balance = 0 WHERE id = :account_id"),
                {"account_id": account_id},
            )
            connection.execute(
                text(
                    "UPDATE loan_repayments SET status = 'paid' "
                    "WHERE loan_application_id <> :application_id AND status = 'scheduled'"
                ),
                {"application_id": int(application["id"])},
            )

        with patch(
            "podobank_api.features.loans.service.write_event_best_effort",
            create=True,
        ) as write_event:
            result = service.process_due_repayments(as_of_date=date.max)

        self.assertEqual(
            (result.processed, result.paid, result.overdue, result.skipped),
            (2, 0, 2, 0),
        )
        self.assertEqual(write_event.call_count, 2)
        events = [call.args[0] for call in write_event.call_args_list]
        self.assertEqual(
            {
                (event["processed"], event["paid"], event["overdue"], event["skipped"])
                for event in events
            },
            {(1, 0, 1, 0)},
        )
        self.assertEqual(len({event["batch_id"] for event in events}), 1)

    def _create_customer(self) -> tuple[int, int]:
        identity = uuid.uuid4().hex
        phone_number = f"010{int(identity[:8], 16) % 100_000_000:08d}"
        account_number = f"3{int(identity[8:19], 16) % 100_000_000_000:011d}"
        with self.engine.begin() as connection:
            user_id = int(
                connection.execute(
                    text(
                        "INSERT INTO users "
                        "(name, phone_number, age, gender, marital_status, is_employed, role) "
                        "VALUES ('financial event customer', :phone, 30, 'female', 'single', "
                        "1, 'customer')"
                    ),
                    {"phone": phone_number},
                ).lastrowid
            )
            account_id = int(
                connection.execute(
                    text(
                        "INSERT INTO accounts (owner_user_id, account_number, balance) "
                        "VALUES (:user_id, :account_number, 0)"
                    ),
                    {"user_id": user_id, "account_number": account_number},
                ).lastrowid
            )
        return user_id, account_id

    def _create_product(self) -> int:
        identity = uuid.uuid4().hex[:10]
        with self.engine.begin() as connection:
            return int(
                connection.execute(
                    text(
                        "INSERT INTO loan_products "
                        "(code, name, principal_amount, term_months, monthly_installment) "
                        "VALUES (:code, 'financial event test product', 2, 2, 1)"
                    ),
                    {"code": f"EVT-{identity}"},
                ).lastrowid
            )
