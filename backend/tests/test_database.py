import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from io import StringIO
from unittest.mock import patch

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from podobank_api import cli as cli_module
from podobank_api import database as database_module
from podobank_api.cli import main as cli_main
from podobank_api.database import (
    DatabaseSafetyError,
    create_database_engine,
    initialize_database,
    reset_database,
    validate_reset_target,
)
from podobank_api.demo_seed import DemoSeedSummary
from podobank_api.features.auth.passwords import verify_password
from podobank_api.seed import DEMO_ACCOUNT_NUMBER, DEMO_CUSTOMER_PHONE, LOAN_PRODUCTS

TEST_EMPLOYEE_PHONE = "01000000009"
TEST_EMPLOYEE_PASSWORD = "test-employee-password"
EXPECTED_TABLES = {
    "users",
    "accounts",
    "ledger_entries",
    "loan_products",
    "loan_applications",
    "loan_repayments",
}


class MariaDBSetupTests(unittest.TestCase):
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

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_initialization_creates_schema_and_is_idempotent(self) -> None:
        initialize_database(
            self.engine,
            employee_phone=TEST_EMPLOYEE_PHONE,
            employee_password=TEST_EMPLOYEE_PASSWORD,
        )
        initialize_database(
            self.engine,
            employee_phone=TEST_EMPLOYEE_PHONE,
            employee_password=TEST_EMPLOYEE_PASSWORD,
        )

        self.assertEqual(
            set(inspect(self.engine).get_table_names()),
            EXPECTED_TABLES,
        )
        with self.engine.connect() as connection:
            user_count = connection.execute(text("SELECT COUNT(*) FROM users")).scalar_one()
            account_count = connection.execute(text("SELECT COUNT(*) FROM accounts")).scalar_one()
            phone = connection.execute(
                text("SELECT phone_number FROM users WHERE phone_number = :phone"),
                {"phone": DEMO_CUSTOMER_PHONE},
            ).scalar_one()
            account_number = connection.execute(
                text("SELECT account_number FROM accounts WHERE account_number = :account_number"),
                {"account_number": DEMO_ACCOUNT_NUMBER},
            ).scalar_one()
            employee_hash = connection.execute(
                text("SELECT password_hash FROM users WHERE phone_number = :phone"),
                {"phone": TEST_EMPLOYEE_PHONE},
            ).scalar_one()
            products = connection.execute(
                text(
                    "SELECT code, name, principal_amount, term_months, monthly_installment "
                    "FROM loan_products ORDER BY code"
                )
            ).all()

        self.assertEqual(user_count, 2)
        self.assertEqual(account_count, 1)
        self.assertEqual(phone, DEMO_CUSTOMER_PHONE)
        self.assertEqual(account_number, DEMO_ACCOUNT_NUMBER)
        self.assertEqual(
            products,
            sorted(
                [
                    (
                        product["code"],
                        product["name"],
                        product["principal_amount"],
                        product["term_months"],
                        product["monthly_installment"],
                    )
                    for product in LOAN_PRODUCTS
                ]
            ),
        )
        self.assertTrue(employee_hash.startswith("$argon2id$"))
        self.assertTrue(verify_password(employee_hash, TEST_EMPLOYEE_PASSWORD))

    def test_mariadb_global_and_session_use_oracle_and_strict_modes(self) -> None:
        with self.engine.connect() as connection:
            global_mode, session_mode = connection.execute(
                text("SELECT @@GLOBAL.sql_mode, @@SESSION.sql_mode")
            ).one()

        for mode in (global_mode, session_mode):
            self.assertIn("ORACLE", mode.split(","))
            self.assertIn("STRICT_TRANS_TABLES", mode.split(","))

    def test_schema_enforces_unique_keys_and_foreign_keys(self) -> None:
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO users (name, phone_number, age, gender, marital_status, "
                        "is_employed, role) VALUES (:name, :phone, 30, 'female', 'single', 1, "
                        "'customer')"
                    ),
                    {"name": "중복 번호", "phone": DEMO_CUSTOMER_PHONE},
                )

        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO users (name, phone_number, kakao_subject, age, gender, "
                        "marital_status, is_employed, role) VALUES (:name, :phone, :subject, "
                        "30, 'female', 'single', 1, 'customer')"
                    ),
                    {
                        "name": "중복 카카오 식별자",
                        "phone": "01000000002",
                        "subject": "demo-kakao-subject",
                    },
                )
                connection.execute(
                    text(
                        "INSERT INTO users (name, phone_number, kakao_subject, age, gender, "
                        "marital_status, is_employed, role) VALUES (:name, :phone, :subject, "
                        "30, 'female', 'single', 1, 'customer')"
                    ),
                    {
                        "name": "중복 카카오 식별자 2",
                        "phone": "01000000003",
                        "subject": "demo-kakao-subject",
                    },
                )

        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO accounts (owner_user_id, account_number) "
                        "VALUES (999999999, '199999999999')"
                    )
                )

    def test_ledger_is_innodb_partitioned_without_foreign_keys(self) -> None:
        inspector = inspect(self.engine)
        primary_key = inspector.get_pk_constraint("ledger_entries")
        indexes = {
            index["name"]: index["column_names"]
            for index in inspector.get_indexes("ledger_entries")
        }
        with self.engine.connect() as connection:
            engines = dict(
                connection.execute(
                    text(
                        "SELECT table_name, engine FROM information_schema.tables "
                        "WHERE table_schema = DATABASE() AND table_name IN "
                        "('accounts', 'ledger_entries', 'loan_products', "
                        "'loan_applications', 'loan_repayments')"
                    )
                ).all()
            )
            partitions = connection.execute(
                text(
                    "SELECT partition_name, partition_description "
                    "FROM information_schema.partitions "
                    "WHERE table_schema = DATABASE() AND table_name = 'ledger_entries' "
                    "ORDER BY partition_ordinal_position"
                )
            ).all()
            foreign_key_columns = connection.execute(
                text(
                    "SELECT table_name, referenced_table_name "
                    "FROM information_schema.key_column_usage "
                    "WHERE table_schema = DATABASE() AND constraint_name <> 'PRIMARY' "
                    "AND (table_name = 'ledger_entries' "
                    "OR referenced_table_name = 'ledger_entries')"
                )
            ).all()

        self.assertEqual(
            engines,
            {
                "accounts": "InnoDB",
                "ledger_entries": "InnoDB",
                "loan_products": "InnoDB",
                "loan_applications": "InnoDB",
                "loan_repayments": "InnoDB",
            },
        )
        self.assertEqual(primary_key["constrained_columns"], ["entry_id", "posted_at"])
        self.assertEqual(
            indexes["ix_ledger_account_posted_entry"],
            ["account_id", "posted_at", "entry_id"],
        )
        self.assertEqual(foreign_key_columns, [])
        self.assertEqual(inspect(self.engine).get_foreign_keys("loan_products"), [])
        application_foreign_keys = {
            tuple(foreign_key["constrained_columns"]): (
                foreign_key["referred_table"],
                tuple(foreign_key["referred_columns"]),
            )
            for foreign_key in inspect(self.engine).get_foreign_keys("loan_applications")
        }
        repayment_foreign_keys = {
            tuple(foreign_key["constrained_columns"]): (
                foreign_key["referred_table"],
                tuple(foreign_key["referred_columns"]),
            )
            for foreign_key in inspect(self.engine).get_foreign_keys("loan_repayments")
        }
        self.assertEqual(
            application_foreign_keys,
            {
                ("user_id",): ("users", ("id",)),
                ("product_id",): ("loan_products", ("id",)),
                ("reviewed_by",): ("users", ("id",)),
            },
        )
        self.assertEqual(
            repayment_foreign_keys,
            {("loan_application_id",): ("loan_applications", ("id",))},
        )

        with self.engine.begin() as connection:
            for suffix, entry_type, amount in (
                (1, "deposit", 1),
                (2, "loan_disbursement", 1),
                (3, "loan_repayment", -1),
            ):
                connection.execute(
                    text(
                        "INSERT INTO ledger_entries "
                        "(posted_at, transaction_id, account_id, user_id, entry_type, amount) "
                        "VALUES (:posted_at, :transaction_id, 999999, 999999, :entry_type, :amount)"
                    ),
                    {
                        "posted_at": datetime(2100, 1, suffix),
                        "transaction_id": f"00000000-0000-4000-8000-{suffix:012d}",
                        "entry_type": entry_type,
                        "amount": amount,
                    },
                )
        with self.engine.connect() as connection:
            future_count = connection.execute(
                text("SELECT COUNT(*) FROM ledger_entries WHERE posted_at >= '2100-01-01'")
            ).scalar_one()
        self.assertEqual(future_count, 3)

        now = datetime.now(UTC)
        current_month = datetime(now.year, now.month, 1)
        expected_names = [f"p_before_{now.year:04d}{now.month:02d}"]
        expected_descriptions = [current_month.strftime("%Y-%m-%d")]
        for offset in range(12):
            year = now.year + (now.month - 1 + offset) // 12
            month = (now.month - 1 + offset) % 12 + 1
            next_year = year + (month == 12)
            next_month = month % 12 + 1
            expected_names.append(f"p_{year:04d}{month:02d}")
            expected_descriptions.append(f"{next_year:04d}-{next_month:02d}-01")
        expected_names.append("p_future")
        expected_descriptions.append("MAXVALUE")
        self.assertEqual([row[0] for row in partitions], expected_names)
        self.assertEqual([str(row[1]).strip("'") for row in partitions], expected_descriptions)

    def test_reset_removes_objects_and_reseeds(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text("CREATE TABLE disposable_table (id BIGINT) ENGINE=InnoDB"))
            connection.execute(
                text("CREATE VIEW disposable_view AS SELECT id FROM disposable_table")
            )

        reset_database(
            self.engine,
            app_env="test",
            employee_phone=TEST_EMPLOYEE_PHONE,
            employee_password=TEST_EMPLOYEE_PASSWORD,
        )

        self.assertEqual(
            set(inspect(self.engine).get_table_names()),
            EXPECTED_TABLES,
        )
        self.assertEqual(inspect(self.engine).get_view_names(), [])
        with self.engine.connect() as connection:
            phone = connection.execute(
                text("SELECT phone_number FROM users WHERE phone_number = :phone"),
                {"phone": DEMO_CUSTOMER_PHONE},
            ).scalar_one()

        self.assertEqual(phone, DEMO_CUSTOMER_PHONE)

    def test_reset_without_seed_leaves_empty_tables_after_initialization(self) -> None:
        reset_database(self.engine, app_env="test", include_seed=False)
        initialize_database(self.engine, include_seed=False)

        with self.engine.connect() as connection:
            user_count = connection.execute(text("SELECT COUNT(*) FROM users")).scalar_one()
            account_count = connection.execute(text("SELECT COUNT(*) FROM accounts")).scalar_one()
            ledger_count = connection.execute(
                text("SELECT COUNT(*) FROM ledger_entries")
            ).scalar_one()
            product_count = connection.execute(
                text("SELECT COUNT(*) FROM loan_products")
            ).scalar_one()
            application_count = connection.execute(
                text("SELECT COUNT(*) FROM loan_applications")
            ).scalar_one()
            repayment_count = connection.execute(
                text("SELECT COUNT(*) FROM loan_repayments")
            ).scalar_one()

        self.assertEqual(user_count, 0)
        self.assertEqual(account_count, 0)
        self.assertEqual(ledger_count, 0)
        self.assertEqual(product_count, 0)
        self.assertEqual(application_count, 0)
        self.assertEqual(repayment_count, 0)

    def test_reset_rejects_non_development_or_test_environment(self) -> None:
        with self.assertRaisesRegex(DatabaseSafetyError, "APP_ENV=development"):
            validate_reset_target("production", self.database_url)

    def test_reset_rejects_another_database_name(self) -> None:
        development_url = self.database_url.rsplit("/", 1)[0] + "/podobank"
        with self.assertRaisesRegex(DatabaseSafetyError, "podobank_dev"):
            validate_reset_target("development", development_url)

    def test_reset_cli_recreates_the_isolated_test_database(self) -> None:
        environment = {"APP_ENV": "test", "DATABASE_URL": self.database_url}
        with patch.dict(os.environ, environment), redirect_stdout(StringIO()):
            exit_code = cli_main(["reset-db", "--no-seed"])

        self.assertEqual(exit_code, 0)
        with self.engine.connect() as connection:
            user_count = connection.execute(text("SELECT COUNT(*) FROM users")).scalar_one()
        self.assertEqual(user_count, 0)

    def test_reset_cli_rejects_production_before_connecting(self) -> None:
        environment = {"APP_ENV": "production", "DATABASE_URL": self.database_url}
        errors = StringIO()
        with patch.dict(os.environ, environment), redirect_stderr(errors):
            exit_code = cli_main(["reset-db"])

        self.assertEqual(exit_code, 2)
        self.assertIn("APP_ENV=development", errors.getvalue())

    def test_seed_demo_data_rejects_unsafe_database_targets(self) -> None:
        validator = getattr(database_module, "validate_demo_seed_target", None)
        if not callable(validator):
            self.fail("validate_demo_seed_target has not been implemented")

        for host in ("db", "localhost", "127.0.0.1"):
            with self.subTest(allowed_host=host):
                validator(
                    "development",
                    f"mysql+pymysql://user:password@{host}:3306/podobank_dev",
                )

        rejected_targets = (
            ("test", "mysql+pymysql://user:password@127.0.0.1:3306/podobank_test"),
            ("production", "mysql+pymysql://user:password@127.0.0.1:3306/podobank_dev"),
            (
                "development",
                "mysql+pymysql://user:password@remote.example.com:3306/podobank_dev",
            ),
            ("development", "mysql+pymysql://user:password@127.0.0.1:3306/podobank_test"),
            ("development", "mysql+pymysql://user:password@127.0.0.1:3307/podobank_dev"),
            (
                "development",
                "mysql+pymysql://user:password@127.0.0.1:3306/podobank_dev?host=remote.example.com",
            ),
            (
                "development",
                "mysql+pymysql://user:password@127.0.0.1:3306/podobank_dev?database=podobank_test",
            ),
            (
                "development",
                "mysql+pymysql://user:password@127.0.0.1:3306/podobank_dev?port=3307",
            ),
        )
        for app_env, database_url in rejected_targets:
            with self.subTest(app_env=app_env, database_url=database_url):
                with self.assertRaises(DatabaseSafetyError):
                    validator(app_env, database_url)

        unsafe_environments = (
            {
                "APP_ENV": "test",
                "DATABASE_URL": "mysql+pymysql://user:password@127.0.0.1:3306/podobank_test",
            },
            {
                "APP_ENV": "production",
                "DATABASE_URL": "mysql+pymysql://user:password@127.0.0.1:3306/podobank_dev",
            },
            {
                "APP_ENV": "development",
                "DATABASE_URL": "mysql+pymysql://user:password@remote.example.com:3306/podobank_dev",
            },
            {
                "APP_ENV": "development",
                "DATABASE_URL": "mysql+pymysql://user:password@127.0.0.1:3306/podobank_dev"
                "?host=remote.example.com",
            },
            {
                "APP_ENV": "development",
                "DATABASE_URL": "mysql+pymysql://user:password@127.0.0.1:3306/podobank_test",
            },
        )
        for environment in unsafe_environments:
            environment["DEMO_CUSTOMER_PASSWORD"] = "local-demo-customer-password"
            errors = StringIO()
            with (
                self.subTest(environment=environment),
                patch.dict(os.environ, environment),
                patch("podobank_api.cli.create_database_engine") as engine_factory,
                redirect_stderr(errors),
            ):
                exit_code = cli_main(["seed-demo-data"])

            self.assertEqual(exit_code, 2)
            engine_factory.assert_not_called()

    def test_seed_demo_data_requires_initialized_database(self) -> None:
        reset_database(self.engine, app_env="test", include_seed=False)
        environment = {
            "APP_ENV": "development",
            "DATABASE_URL": "mysql+pymysql://user:password@127.0.0.1:3306/podobank_dev",
            "DEMO_CUSTOMER_PASSWORD": "local-demo-customer-password",
        }
        errors = StringIO()
        with (
            patch.dict(os.environ, environment),
            patch("podobank_api.cli.create_database_engine", return_value=self.engine),
            patch.object(cli_module, "seed_demo_data", create=True) as seed_builder,
            redirect_stderr(errors),
        ):
            exit_code = cli_main(["seed-demo-data"])

        self.assertEqual(exit_code, 2)
        self.assertIn("init-db", errors.getvalue())
        seed_builder.assert_not_called()

    def test_seed_demo_data_command_reports_counts_without_secrets(self) -> None:
        secret = "local-demo-customer-password"
        summary = DemoSeedSummary(
            already_present=False,
            customer_count=10_000,
            account_count=10_000,
            ledger_entry_count=200_000,
            loan_application_count=500,
            repayment_count=18_000,
        )
        environment = {
            "APP_ENV": "development",
            "DATABASE_URL": "mysql+pymysql://user:password@127.0.0.1:3306/podobank_dev",
            "DEMO_CUSTOMER_PASSWORD": secret,
            "BANK_EMPLOYEE_PHONE": TEST_EMPLOYEE_PHONE,
        }
        output = StringIO()
        with (
            patch.dict(os.environ, environment),
            patch("podobank_api.cli.create_database_engine", return_value=self.engine),
            patch(
                "podobank_api.cli.seed_demo_data", return_value=summary, create=True
            ) as seed_builder,
            redirect_stdout(output),
        ):
            exit_code = cli_main(["seed-demo-data"])

        self.assertEqual(exit_code, 0)
        self.assertIn("customers=10000", output.getvalue())
        self.assertIn("accounts=10000", output.getvalue())
        self.assertIn("ledger_entries=200000", output.getvalue())
        self.assertIn("loan_applications=500", output.getvalue())
        self.assertIn("repayments=18000", output.getvalue())
        self.assertNotIn(secret, output.getvalue())
        seed_builder.assert_called_once()
        self.assertEqual(
            seed_builder.call_args.kwargs["demo_customer_password"],
            secret,
        )
