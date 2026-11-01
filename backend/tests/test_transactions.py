import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from podobank_api.app import create_app
from podobank_api.database import create_database_engine, reset_database, validate_reset_target
from podobank_api.features.auth.tokens import SESSION_COOKIE_NAME, issue_session_token
from podobank_api.features.transactions import sql as transaction_sql
from podobank_api.features.transactions.service import (
    MAX_BALANCE,
    InsufficientFundsError,
    TransactionService,
)
from podobank_api.seed import DEMO_CUSTOMER_PHONE
from podobank_api.settings import Settings

TEST_EMPLOYEE_PHONE = "01000000009"
TEST_EMPLOYEE_PASSWORD = "test-employee-password"
SOURCE_ACCOUNT_NUMBER = "100000000101"
DESTINATION_ACCOUNT_NUMBER = "100000000102"
OTHER_ACCOUNT_NUMBER = "100000000103"
SOURCE_PHONE = "01011110001"
DESTINATION_PHONE = "01011110002"
OTHER_PHONE = "01011110003"


class MoneyMovementApiTests(unittest.TestCase):
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
            self.source_user_id = self._insert_customer(
                connection, "보내는 고객", SOURCE_PHONE, SOURCE_ACCOUNT_NUMBER
            )
            self.destination_user_id = self._insert_customer(
                connection, "받는 고객", DESTINATION_PHONE, DESTINATION_ACCOUNT_NUMBER
            )
            self.other_user_id = self._insert_customer(
                connection, "다른 고객", OTHER_PHONE, OTHER_ACCOUNT_NUMBER
            )
            self.source_account_id = self._account_id(connection, SOURCE_ACCOUNT_NUMBER)
            self.destination_account_id = self._account_id(connection, DESTINATION_ACCOUNT_NUMBER)
            self.other_account_id = self._account_id(connection, OTHER_ACCOUNT_NUMBER)
            self.demo_user_id = int(
                connection.execute(
                    text("SELECT id FROM users WHERE phone_number = :phone"),
                    {"phone": DEMO_CUSTOMER_PHONE},
                ).scalar_one()
            )
            self.employee_user_id = int(
                connection.execute(
                    text("SELECT id FROM users WHERE phone_number = :phone"),
                    {"phone": TEST_EMPLOYEE_PHONE},
                ).scalar_one()
            )

        self.app = create_app(self.settings, engine=self.engine)
        self.client = TestClient(self.app)

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

    @staticmethod
    def _account_id(connection, account_number: str) -> int:
        return int(
            connection.execute(
                text("SELECT id FROM accounts WHERE account_number = :account_number"),
                {"account_number": account_number},
            ).scalar_one()
        )

    def _client_as(self, user_id: int) -> TestClient:
        self.client.cookies.set(
            SESSION_COOKIE_NAME,
            issue_session_token(user_id, self.settings),
        )
        return self.client

    def _balance(self, account_id: int) -> int:
        with self.engine.connect() as connection:
            return int(
                connection.execute(
                    text("SELECT balance FROM accounts WHERE id = :account_id"),
                    {"account_id": account_id},
                ).scalar_one()
            )

    def _ledger_rows(self, account_id: int | None = None) -> list[dict[str, object]]:
        where = " WHERE account_id = :account_id" if account_id is not None else ""
        parameters = {"account_id": account_id} if account_id is not None else {}
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT entry_id, posted_at, transaction_id, account_id, user_id, "
                    "entry_type, amount FROM ledger_entries"
                    f"{where} ORDER BY posted_at, entry_id"
                ),
                parameters,
            ).mappings()
            return [dict(row) for row in rows]

    def test_deposit_and_withdrawal_update_balance_with_signed_ledger_rows(self) -> None:
        client = self._client_as(self.source_user_id)
        deposit = client.post("/transactions/deposit", json={"amount": 25_000})
        withdrawal = client.post("/transactions/withdrawal", json={"amount": 7_000})

        self.assertEqual(deposit.status_code, 200)
        self.assertEqual(deposit.json()["balance"], 25_000)
        self.assertEqual(withdrawal.status_code, 200)
        self.assertEqual(withdrawal.json()["balance"], 18_000)
        rows = self._ledger_rows(self.source_account_id)
        self.assertEqual([row["entry_type"] for row in rows], ["deposit", "withdrawal"])
        self.assertEqual([row["amount"] for row in rows], [25_000, -7_000])
        self.assertEqual(self._balance(self.source_account_id), 18_000)

    def test_rejected_amount_and_insufficient_withdrawal_change_neither_balance_nor_ledger(self):
        client = self._client_as(self.source_user_id)
        invalid = client.post("/transactions/deposit", json={"amount": 0})
        insufficient = client.post("/transactions/withdrawal", json={"amount": 1})

        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(insufficient.status_code, 409)
        self.assertEqual(self._balance(self.source_account_id), 0)
        self.assertEqual(self._ledger_rows(), [])

    def test_transfer_uses_recipient_lookup_and_writes_a_paired_transaction(self) -> None:
        client = self._client_as(self.source_user_id)
        deposit = client.post("/transactions/deposit", json={"amount": 20_000})
        self.assertEqual(deposit.status_code, 200)

        recipient = client.post("/accounts/recipients/search", json={"query": DESTINATION_PHONE})
        self.assertEqual(recipient.status_code, 200)
        item = recipient.json()["items"][0]
        self.assertEqual(item["account_id"], self.destination_account_id)
        self.assertEqual(item["masked_account_number"], "••••0102")
        self.assertEqual(item["phone_suffix"], DESTINATION_PHONE[-4:])
        self.assertNotIn(DESTINATION_PHONE, recipient.text)
        self.assertNotIn(DESTINATION_ACCOUNT_NUMBER, recipient.text)

        transfer = client.post(
            "/transactions/transfer",
            json={"destination_account_id": item["account_id"], "amount": 8_000},
        )
        self.assertEqual(transfer.status_code, 200)
        self.assertEqual(transfer.json()["balance"], 12_000)
        self.assertEqual(self._balance(self.source_account_id), 12_000)
        self.assertEqual(self._balance(self.destination_account_id), 8_000)

        paired = [
            row
            for row in self._ledger_rows()
            if row["transaction_id"] == transfer.json()["transaction_id"]
        ]
        self.assertEqual(len(paired), 2)
        self.assertEqual({row["entry_type"] for row in paired}, {"transfer_out", "transfer_in"})
        self.assertEqual(sum(int(row["amount"]) for row in paired), 0)
        self.assertEqual(
            {int(row["account_id"]) for row in paired},
            {self.source_account_id, self.destination_account_id},
        )

    def test_recipient_search_by_account_number_and_list_excludes_self(self) -> None:
        client = self._client_as(self.source_user_id)
        by_account = client.post(
            "/accounts/recipients/search", json={"query": DESTINATION_ACCOUNT_NUMBER}
        )
        listed = client.get("/accounts/recipients", params={"limit": 100})

        self.assertEqual(by_account.status_code, 200)
        self.assertEqual(
            [item["account_id"] for item in by_account.json()["items"]],
            [self.destination_account_id],
        )
        listed_ids = {item["account_id"] for item in listed.json()["items"]}
        self.assertIn(self.destination_account_id, listed_ids)
        self.assertIn(self.other_account_id, listed_ids)
        self.assertNotIn(self.source_account_id, listed_ids)

    def test_ledger_date_bounds_and_pagination_are_account_scoped(self) -> None:
        client = self._client_as(self.source_user_id)
        client.post("/transactions/deposit", json={"amount": 100})
        client.post("/transactions/deposit", json={"amount": 200})
        lower = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        upper = (datetime.now(UTC) + timedelta(days=1)).isoformat()

        response = client.get(
            "/accounts/me/ledger",
            params={"start_at": lower, "end_at": upper, "limit": 1, "offset": 1},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["limit"], 1)
        self.assertEqual(len(response.json()["items"]), 1)
        self.assertEqual(response.json()["items"][0]["amount"], 100)
        self.assertTrue(response.json()["items"][0]["posted_at"].endswith("Z"))

        invalid_bounds = client.get(
            "/accounts/me/ledger",
            params={"start_at": upper, "end_at": lower},
        )
        naive_bound = client.get("/accounts/me/ledger", params={"start_at": "2026-01-01T00:00:00"})
        self.assertEqual(invalid_bounds.status_code, 422)
        self.assertEqual(naive_bound.status_code, 422)

        self._client_as(self.destination_user_id)
        other_account_ledger = self.client.get("/accounts/me/ledger")
        self.assertEqual(other_account_ledger.status_code, 200)
        self.assertEqual(other_account_ledger.json()["items"], [])

    def test_customer_authentication_is_required_for_money_movement_and_recipients(self) -> None:
        unauthenticated = TestClient(self.app)
        try:
            self.assertEqual(
                unauthenticated.post("/transactions/deposit", json={"amount": 1}).status_code,
                401,
            )
            self.assertEqual(unauthenticated.get("/accounts/recipients").status_code, 401)
        finally:
            unauthenticated.close()

        employee = self._client_as(self.employee_user_id)
        response = employee.post("/transactions/deposit", json={"amount": 1})
        self.assertEqual(response.status_code, 403)

    def test_transfer_rejects_self_unknown_and_insufficient_without_partial_writes(self) -> None:
        client = self._client_as(self.source_user_id)
        self_transfer = client.post(
            "/transactions/transfer",
            json={"destination_account_id": self.source_account_id, "amount": 1},
        )
        unknown_recipient = client.post(
            "/transactions/transfer",
            json={"destination_account_id": 9_999_999, "amount": 1},
        )
        insufficient = client.post(
            "/transactions/transfer",
            json={"destination_account_id": self.destination_account_id, "amount": 1},
        )

        self.assertEqual(self_transfer.status_code, 422)
        self.assertEqual(unknown_recipient.status_code, 404)
        self.assertEqual(insufficient.status_code, 409)
        self.assertEqual(self._balance(self.source_account_id), 0)
        self.assertEqual(self._balance(self.destination_account_id), 0)
        self.assertEqual(self._ledger_rows(), [])

    def test_transfer_rejects_destination_balance_overflow_without_partial_writes(self) -> None:
        service = TransactionService(self.engine)
        service.deposit(user_id=self.source_user_id, amount=10)
        with self.engine.begin() as connection:
            connection.execute(
                text("UPDATE accounts SET balance = :balance WHERE id = :account_id"),
                {"balance": MAX_BALANCE, "account_id": self.destination_account_id},
            )

        response = self._client_as(self.source_user_id).post(
            "/transactions/transfer",
            json={"destination_account_id": self.destination_account_id, "amount": 1},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self._balance(self.source_account_id), 10)
        self.assertEqual(self._balance(self.destination_account_id), MAX_BALANCE)
        self.assertEqual([row["entry_type"] for row in self._ledger_rows()], ["deposit"])

    def test_transfer_ledger_failure_rolls_back_both_balances_and_both_entries(self) -> None:
        service = TransactionService(self.engine)
        service.deposit(user_id=self.source_user_id, amount=5_000)
        original_insert = transaction_sql.insert_ledger_entry
        calls = 0

        def fail_after_first_entry(*args, **kwargs) -> None:
            nonlocal calls
            calls += 1
            original_insert(*args, **kwargs)
            if calls == 2:
                raise RuntimeError("simulated ledger failure")

        with patch.object(
            transaction_sql,
            "insert_ledger_entry",
            side_effect=fail_after_first_entry,
        ):
            with self.assertRaisesRegex(RuntimeError, "simulated ledger failure"):
                service.transfer(
                    user_id=self.source_user_id,
                    destination_account_id=self.destination_account_id,
                    amount=2_000,
                )

        self.assertEqual(self._balance(self.source_account_id), 5_000)
        self.assertEqual(self._balance(self.destination_account_id), 0)
        self.assertEqual([row["entry_type"] for row in self._ledger_rows()], ["deposit"])

    def test_concurrent_withdrawals_cannot_drive_balance_negative(self) -> None:
        service = TransactionService(self.engine)
        service.deposit(user_id=self.source_user_id, amount=1_000)

        def withdraw() -> str:
            try:
                service.withdraw(user_id=self.source_user_id, amount=400)
            except InsufficientFundsError:
                return "insufficient"
            return "withdrawn"

        with ThreadPoolExecutor(max_workers=4) as executor:
            outcomes = list(executor.map(lambda _: withdraw(), range(4)))

        self.assertEqual(outcomes.count("withdrawn"), 2)
        self.assertEqual(outcomes.count("insufficient"), 2)
        self.assertEqual(self._balance(self.source_account_id), 200)
        self.assertGreaterEqual(self._balance(self.source_account_id), 0)

    def test_opposing_concurrent_transfers_remain_paired(self) -> None:
        service = TransactionService(self.engine)
        service.deposit(user_id=self.source_user_id, amount=100)
        service.deposit(user_id=self.destination_user_id, amount=100)

        def transfer(args: tuple[int, int]) -> None:
            user_id, destination_id = args
            service.transfer(user_id=user_id, destination_account_id=destination_id, amount=1)

        operations = [
            (self.source_user_id, self.destination_account_id),
            (self.destination_user_id, self.source_account_id),
        ] * 20
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(transfer, operations))

        self.assertEqual(self._balance(self.source_account_id), 100)
        self.assertEqual(self._balance(self.destination_account_id), 100)
        transfers = [
            row for row in self._ledger_rows() if row["entry_type"].startswith("transfer_")
        ]
        by_transaction: dict[str, list[dict[str, object]]] = {}
        for entry in transfers:
            by_transaction.setdefault(str(entry["transaction_id"]), []).append(entry)
        self.assertEqual(len(by_transaction), 40)
        for entries in by_transaction.values():
            self.assertEqual(len(entries), 2)
            self.assertEqual(sum(int(entry["amount"]) for entry in entries), 0)

    def test_operation_logs_do_not_include_amount_account_or_phone(self) -> None:
        client = self._client_as(self.source_user_id)
        amount = 876_543_210
        with self.assertLogs("podobank_api.features.transactions.service", level="INFO") as logs:
            response = client.post("/transactions/deposit", json={"amount": amount})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            logs.output,
            [
                "INFO:podobank_api.features.transactions.service:"
                "financial_operation operation=deposit outcome=success reason=completed"
            ],
        )
        self.assertNotIn(str(amount), logs.output[0])
        self.assertNotIn(SOURCE_ACCOUNT_NUMBER, logs.output[0])
        self.assertNotIn(SOURCE_PHONE, logs.output[0])

    def test_database_errors_do_not_expose_bound_phone_values(self) -> None:
        client = self._client_as(self.source_user_id)
        database_error = OperationalError(
            "recipient lookup failed",
            {"phone_number": DESTINATION_PHONE},
            RuntimeError("database error"),
        )
        with patch(
            "podobank_api.features.accounts.sql.find_recipients",
            side_effect=database_error,
        ):
            response = client.post("/accounts/recipients/search", json={"query": DESTINATION_PHONE})

        self.assertEqual(response.status_code, 503)
        self.assertNotIn(DESTINATION_PHONE, response.text)
        self.assertEqual(
            response.json()["detail"]["code"],
            "database_unavailable",
        )
