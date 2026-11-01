import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import patch

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from podobank_api.cli import main as cli_main
from podobank_api.database import (
    DatabaseSafetyError,
    create_database_engine,
    initialize_database,
    reset_database,
    validate_reset_target,
)
from podobank_api.seed import DEMO_ACCOUNT_NUMBER, DEMO_CUSTOMER_PHONE


class MariaDBSetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_url = os.environ.get("DATABASE_URL", "")
        if not self.database_url:
            self.fail("DATABASE_URL must point to the isolated podobank_test database")
        validate_reset_target("test", self.database_url)
        self.engine = create_database_engine(self.database_url)
        reset_database(self.engine, app_env="test")

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_initialization_creates_schema_and_is_idempotent(self) -> None:
        initialize_database(self.engine)
        initialize_database(self.engine)

        self.assertEqual(set(inspect(self.engine).get_table_names()), {"users", "accounts"})
        with self.engine.connect() as connection:
            user_count = connection.execute(text("SELECT COUNT(*) FROM users")).scalar_one()
            account_count = connection.execute(text("SELECT COUNT(*) FROM accounts")).scalar_one()
            phone = connection.execute(text("SELECT phone_number FROM users")).scalar_one()
            account_number = connection.execute(
                text("SELECT account_number FROM accounts")
            ).scalar_one()

        self.assertEqual(user_count, 1)
        self.assertEqual(account_count, 1)
        self.assertEqual(phone, DEMO_CUSTOMER_PHONE)
        self.assertEqual(account_number, DEMO_ACCOUNT_NUMBER)

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

    def test_reset_removes_objects_and_reseeds(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text("CREATE TABLE disposable_table (id BIGINT) ENGINE=InnoDB"))
            connection.execute(
                text("CREATE VIEW disposable_view AS SELECT id FROM disposable_table")
            )

        reset_database(self.engine, app_env="test")

        self.assertEqual(set(inspect(self.engine).get_table_names()), {"users", "accounts"})
        self.assertEqual(inspect(self.engine).get_view_names(), [])
        with self.engine.connect() as connection:
            phone = connection.execute(text("SELECT phone_number FROM users")).scalar_one()

        self.assertEqual(phone, DEMO_CUSTOMER_PHONE)

    def test_reset_without_seed_leaves_empty_tables_after_initialization(self) -> None:
        reset_database(self.engine, app_env="test", include_seed=False)
        initialize_database(self.engine)

        with self.engine.connect() as connection:
            user_count = connection.execute(text("SELECT COUNT(*) FROM users")).scalar_one()
            account_count = connection.execute(text("SELECT COUNT(*) FROM accounts")).scalar_one()

        self.assertEqual(user_count, 0)
        self.assertEqual(account_count, 0)

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
