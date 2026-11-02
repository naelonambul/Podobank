import os
import unittest
from collections import Counter
from datetime import date, datetime

from sqlalchemy import text

from podobank_api.database import create_database_engine, reset_database, validate_reset_target
from podobank_api.features.auth.passwords import hash_password, verify_password
from podobank_api.seed import DEMO_CUSTOMER_PHONE

TEST_EMPLOYEE_PHONE = "01000000009"
TEST_EMPLOYEE_PASSWORD = "test-employee-password"
DEMO_PASSWORD = "local-demo-password"
SMALL_CUSTOMER_COUNT = 12
SMALL_LEDGER_ENTRIES_PER_CUSTOMER = 4
SMALL_LOAN_APPLICATION_COUNT = 10


def normalize_date(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value


def demo_seed_module(test_case: unittest.TestCase):
    try:
        from podobank_api import demo_seed
    except ImportError:
        test_case.fail("the demo sample data builder has not been implemented")
    return demo_seed


class DemoSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        database_url = os.environ.get("DATABASE_URL", "")
        if not database_url:
            self.fail("DATABASE_URL must point to the isolated podobank_test database")
        validate_reset_target("test", database_url)
        self.engine = create_database_engine(database_url)
        reset_database(
            self.engine,
            app_env="test",
            employee_phone=TEST_EMPLOYEE_PHONE,
            employee_password=TEST_EMPLOYEE_PASSWORD,
        )

    def tearDown(self) -> None:
        self.engine.dispose()

    def _seed(self, *, loan_application_count: int = SMALL_LOAN_APPLICATION_COUNT):
        demo_seed = demo_seed_module(self)
        with self.engine.begin() as connection:
            return demo_seed.seed_demo_data(
                connection,
                demo_customer_password=DEMO_PASSWORD,
                customer_count=SMALL_CUSTOMER_COUNT,
                ledger_entries_per_customer=SMALL_LEDGER_ENTRIES_PER_CUSTOMER,
                loan_application_count=loan_application_count,
            )

    def test_seed_coexists_with_existing_ui_verification_customer(self) -> None:
        with self.engine.begin() as connection:
            fixture_id = int(
                connection.execute(
                    text(
                        "INSERT INTO users (name, phone_number, age, gender, marital_status, "
                        "is_employed, role) VALUES ('UI 수취인 fixture', '01099990001', 30, "
                        "'female', 'single', 1, 'customer')"
                    )
                ).lastrowid
            )
            connection.execute(
                text(
                    "INSERT INTO accounts (owner_user_id, account_number, balance) "
                    "VALUES (:owner_user_id, '200000000001', 0)"
                ),
                {"owner_user_id": fixture_id},
            )

        summary = self._seed(loan_application_count=0)

        with self.engine.connect() as connection:
            fixture = connection.execute(
                text(
                    "SELECT u.id, u.phone_number, a.account_number FROM users AS u "
                    "JOIN accounts AS a ON a.owner_user_id = u.id WHERE u.id = :user_id"
                ),
                {"user_id": fixture_id},
            ).one()
            customer_count = connection.execute(
                text("SELECT COUNT(*) FROM users WHERE role = 'customer'")
            ).scalar_one()

        self.assertEqual(fixture.phone_number, "01099990001")
        self.assertEqual(fixture.account_number, "200000000001")
        self.assertEqual(customer_count, SMALL_CUSTOMER_COUNT + 1)
        self.assertEqual(summary.customer_count, SMALL_CUSTOMER_COUNT)

    def test_small_seed_creates_fixed_customer_and_one_account_per_customer(self) -> None:
        summary = self._seed(loan_application_count=0)

        with self.engine.connect() as connection:
            customer_count = connection.execute(
                text("SELECT COUNT(*) FROM users WHERE role = 'customer'")
            ).scalar_one()
            account_count = connection.execute(text("SELECT COUNT(*) FROM accounts")).scalar_one()
            demo_customer = (
                connection.execute(
                    text(
                        "SELECT id, name, password_hash FROM users "
                        "WHERE phone_number = :phone_number"
                    ),
                    {"phone_number": DEMO_CUSTOMER_PHONE},
                )
                .mappings()
                .one()
            )
            demo_account = connection.execute(
                text("SELECT owner_user_id FROM accounts WHERE account_number = '100000000001'")
            ).scalar_one()

        self.assertEqual(customer_count, SMALL_CUSTOMER_COUNT)
        self.assertEqual(account_count, SMALL_CUSTOMER_COUNT)
        self.assertEqual(summary.customer_count, SMALL_CUSTOMER_COUNT)
        self.assertEqual(summary.account_count, SMALL_CUSTOMER_COUNT)
        self.assertEqual(demo_customer["name"], "가상 고객 1")
        self.assertEqual(demo_account, demo_customer["id"])
        self.assertTrue(verify_password(demo_customer["password_hash"], DEMO_PASSWORD))

    def test_seeded_activity_reconciles_balances_and_pairs_transfers(self) -> None:
        summary = self._seed(loan_application_count=0)

        with self.engine.connect() as connection:
            account_rows = connection.execute(
                text(
                    "SELECT a.id, a.balance, COALESCE(SUM(l.amount), 0) AS ledger_balance, "
                    "COUNT(l.entry_id) AS entry_count "
                    "FROM accounts AS a LEFT JOIN ledger_entries AS l ON l.account_id = a.id "
                    "GROUP BY a.id, a.balance ORDER BY a.id"
                )
            ).all()
            transfer_groups = connection.execute(
                text(
                    "SELECT transaction_id, COUNT(*) AS entry_count, SUM(amount) AS net_amount "
                    "FROM ledger_entries WHERE entry_type IN ('transfer_in', 'transfer_out') "
                    "GROUP BY transaction_id"
                )
            ).all()
            ledger_count = connection.execute(
                text("SELECT COUNT(*) FROM ledger_entries")
            ).scalar_one()

        self.assertEqual(len(account_rows), SMALL_CUSTOMER_COUNT)
        for row in account_rows:
            self.assertGreaterEqual(row.balance, 0)
            self.assertEqual(row.balance, row.ledger_balance)
            self.assertEqual(row.entry_count, SMALL_LEDGER_ENTRIES_PER_CUSTOMER)
        self.assertTrue(transfer_groups)
        self.assertTrue(
            all(row.entry_count == 2 and row.net_amount == 0 for row in transfer_groups)
        )
        self.assertEqual(ledger_count, summary.ledger_entry_count)

    def test_demo_customer_password_is_hashed_when_unset_and_preserved_when_set(self) -> None:
        self._seed(loan_application_count=0)
        with self.engine.connect() as connection:
            stored_hash = connection.execute(
                text("SELECT password_hash FROM users WHERE phone_number = :phone_number"),
                {"phone_number": DEMO_CUSTOMER_PHONE},
            ).scalar_one()
        self.assertTrue(stored_hash.startswith("$argon2id$"))
        self.assertTrue(verify_password(stored_hash, DEMO_PASSWORD))

        reset_database(
            self.engine,
            app_env="test",
            employee_phone=TEST_EMPLOYEE_PHONE,
            employee_password=TEST_EMPLOYEE_PASSWORD,
        )
        original_hash = hash_password("customer-chosen-password")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE users SET password_hash = :password_hash "
                    "WHERE phone_number = :phone_number"
                ),
                {"password_hash": original_hash, "phone_number": DEMO_CUSTOMER_PHONE},
            )
        self._seed(loan_application_count=0)

        with self.engine.connect() as connection:
            preserved_hash = connection.execute(
                text("SELECT password_hash FROM users WHERE phone_number = :phone_number"),
                {"phone_number": DEMO_CUSTOMER_PHONE},
            ).scalar_one()
        self.assertEqual(preserved_hash, original_hash)
        self.assertTrue(verify_password(preserved_hash, "customer-chosen-password"))
        self.assertFalse(verify_password(preserved_hash, DEMO_PASSWORD))

    def test_small_loan_seed_has_each_state_valid_schedules_and_one_active_loan(self) -> None:
        demo_seed = demo_seed_module(self)
        self._seed()

        with self.engine.connect() as connection:
            applications = (
                connection.execute(
                    text(
                        "SELECT id, user_id, status, term_months, approved_at "
                        "FROM loan_applications ORDER BY id"
                    )
                )
                .mappings()
                .all()
            )
            status_counts = dict(
                connection.execute(
                    text("SELECT status, COUNT(*) FROM loan_applications GROUP BY status")
                ).all()
            )
            active_duplicates = connection.execute(
                text(
                    "SELECT COUNT(*) FROM (SELECT user_id FROM loan_applications "
                    "WHERE status IN ('pending', 'repaying') GROUP BY user_id "
                    "HAVING COUNT(*) > 1) AS duplicate_active_loans"
                )
            ).scalar_one()
            repayment_rows = (
                connection.execute(
                    text(
                        "SELECT r.loan_application_id, r.installment_number, r.due_date, "
                        "r.amount, r.status, r.processed_at, r.paid_at "
                        "FROM loan_repayments AS r ORDER BY r.loan_application_id, "
                        "r.installment_number"
                    )
                )
                .mappings()
                .all()
            )

        self.assertEqual(len(applications), SMALL_LOAN_APPLICATION_COUNT)
        self.assertEqual(status_counts, {"pending": 2, "rejected": 2, "repaying": 5, "repaid": 1})
        self.assertEqual(active_duplicates, 0)
        self.assertEqual(applications[0]["status"], "repaying")
        self.assertTrue(repayment_rows)

        by_application: dict[int, list[object]] = {}
        for row in repayment_rows:
            by_application.setdefault(int(row["loan_application_id"]), []).append(row)
            self.assertGreater(row["amount"], 0)
        for application in applications:
            rows = by_application.get(int(application["id"]), [])
            if application["status"] in {"pending", "rejected"}:
                self.assertEqual(rows, [])
                continue

            expected_dates = demo_seed.repayment_due_dates(
                application["approved_at"], int(application["term_months"])
            )
            self.assertEqual(len(rows), int(application["term_months"]))
            self.assertEqual(
                [normalize_date(row["due_date"]) for row in rows],
                expected_dates,
            )
            if application["status"] == "repaid":
                self.assertTrue(all(row["status"] == "paid" for row in rows))
                self.assertTrue(all(row["paid_at"] is not None for row in rows))
            else:
                self.assertTrue(any(row["status"] == "paid" for row in rows))
                self.assertTrue(any(row["status"] == "overdue" for row in rows))
                self.assertTrue(any(row["status"] == "scheduled" for row in rows))
                overdue_rows = [row for row in rows if row["status"] == "overdue"]
                self.assertTrue(
                    all(normalize_date(row["due_date"]) < date.today() for row in overdue_rows)
                )

    def test_default_loan_distribution_is_one_hundred_five_hundred_split(self) -> None:
        demo_seed = demo_seed_module(self)

        self.assertEqual(
            demo_seed.DEMO_LOAN_STATUS_COUNTS,
            {"pending": 100, "rejected": 100, "repaying": 250, "repaid": 50},
        )
        self.assertEqual(sum(demo_seed.DEMO_LOAN_STATUS_COUNTS.values()), 500)
        self.assertEqual(
            Counter(demo_seed._loan_statuses(demo_seed.DEMO_LOAN_APPLICATION_COUNT)),
            demo_seed.DEMO_LOAN_STATUS_COUNTS,
        )

    def test_repeating_complete_seed_is_a_noop(self) -> None:
        first = self._seed()
        first_counts = self._database_counts()
        second = self._seed()
        second_counts = self._database_counts()

        self.assertFalse(first.already_present)
        self.assertTrue(second.already_present)
        self.assertEqual(
            (
                first.customer_count,
                first.account_count,
                first.ledger_entry_count,
                first.loan_application_count,
                first.repayment_count,
            ),
            (
                second.customer_count,
                second.account_count,
                second.ledger_entry_count,
                second.loan_application_count,
                second.repayment_count,
            ),
        )
        self.assertEqual(first_counts, second_counts)

    def test_partial_sample_namespace_fails_without_deleting_remaining_rows(self) -> None:
        self._seed()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM ledger_entries WHERE entry_id = ("
                    "SELECT entry_id FROM (SELECT entry_id FROM ledger_entries "
                    "ORDER BY entry_id LIMIT 1) AS first_sample_entry)"
                )
            )
        before = self._database_counts()

        with self.assertRaises(ValueError):
            self._seed()

        self.assertEqual(self._database_counts(), before)

    def _database_counts(self) -> tuple[int, ...]:
        with self.engine.connect() as connection:
            return tuple(
                int(connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one())
                for table_name in (
                    "users",
                    "accounts",
                    "ledger_entries",
                    "loan_applications",
                    "loan_repayments",
                )
            )
