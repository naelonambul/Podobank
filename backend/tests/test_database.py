import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import inspect

from podobank_api.cli import main as cli_main
from podobank_api.database import (
    DatabaseSafetyError,
    create_database_engine,
    initialize_database,
    reset_database,
    validate_reset_target,
)
from podobank_api.seed import DEMO_ACCOUNT_NUMBER, DEMO_CUSTOMER_PHONE

EXPECTED_SCHEMA_TABLES = {
    "schema_meta",
    "users",
    "accounts",
    "transaction_entries",
    "loan_products",
    "loans",
    "loan_installments",
}


class DatabaseSetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "podobank.db"
        self.database_url = f"sqlite:///{self.database_path}"
        self.engine = create_database_engine(self.database_url)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.temporary_directory.cleanup()

    def test_initialization_creates_schema_and_is_idempotent(self) -> None:
        initialize_database(self.engine)
        initialize_database(self.engine)

        self.assertEqual(set(inspect(self.engine).get_table_names()), EXPECTED_SCHEMA_TABLES)
        with self.engine.connect() as connection:
            user_count = connection.exec_driver_sql("SELECT COUNT(*) FROM users").scalar_one()
            account_count = connection.exec_driver_sql("SELECT COUNT(*) FROM accounts").scalar_one()
            foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()

        self.assertEqual(user_count, 4)
        self.assertEqual(account_count, 3)
        self.assertEqual(foreign_keys, 1)

    def test_reset_removes_all_existing_tables_and_reseeds(self) -> None:
        initialize_database(self.engine)
        with self.engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE disposable_table (id INTEGER)")

        reset_database(self.engine, app_env="development")

        self.assertEqual(set(inspect(self.engine).get_table_names()), EXPECTED_SCHEMA_TABLES)
        with self.engine.connect() as connection:
            phone = connection.exec_driver_sql(
                "SELECT phone_number FROM users WHERE phone_number = ?",
                (DEMO_CUSTOMER_PHONE,),
            ).scalar_one()
            account_number = connection.exec_driver_sql(
                "SELECT account_number FROM accounts WHERE account_number = ?",
                (DEMO_ACCOUNT_NUMBER,),
            ).scalar_one()

        self.assertEqual(phone, DEMO_CUSTOMER_PHONE)
        self.assertEqual(account_number, DEMO_ACCOUNT_NUMBER)

    def test_reset_without_seed_leaves_empty_tables(self) -> None:
        reset_database(self.engine, app_env="development", include_seed=False)

        with self.engine.connect() as connection:
            user_count = connection.exec_driver_sql("SELECT COUNT(*) FROM users").scalar_one()
            account_count = connection.exec_driver_sql("SELECT COUNT(*) FROM accounts").scalar_one()

        self.assertEqual(user_count, 0)
        self.assertEqual(account_count, 0)

    def test_startup_does_not_reseed_database_reset_without_seed(self) -> None:
        reset_database(self.engine, app_env="development", include_seed=False)

        initialize_database(self.engine)

        with self.engine.connect() as connection:
            user_count = connection.exec_driver_sql("SELECT COUNT(*) FROM users").scalar_one()
            account_count = connection.exec_driver_sql("SELECT COUNT(*) FROM accounts").scalar_one()

        self.assertEqual(user_count, 0)
        self.assertEqual(account_count, 0)

    def test_reset_drops_views_before_recreating_schema(self) -> None:
        with self.engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE view_source (id INTEGER)")
            connection.exec_driver_sql("CREATE VIEW users AS SELECT id FROM view_source")
            connection.exec_driver_sql("CREATE VIEW accounts AS SELECT id FROM view_source")
            connection.exec_driver_sql("CREATE VIEW disposable_view AS SELECT id FROM view_source")

        reset_database(self.engine, app_env="development")

        self.assertEqual(set(inspect(self.engine).get_table_names()), EXPECTED_SCHEMA_TABLES)
        self.assertEqual(inspect(self.engine).get_view_names(), [])

    def test_reset_rejects_non_development_environment(self) -> None:
        with self.assertRaisesRegex(DatabaseSafetyError, "APP_ENV=development"):
            validate_reset_target("production", self.database_url)

    def test_reset_rejects_non_sqlite_database_before_connecting(self) -> None:
        with self.assertRaisesRegex(DatabaseSafetyError, "SQLite"):
            validate_reset_target(
                "development",
                "mariadb+pymysql://user:password@localhost/podobank",
            )


class DatabaseCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "cli.db"
        self.database_url = f"sqlite:///{self.database_path}"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_reset_cli_supports_empty_database(self) -> None:
        environment = {"APP_ENV": "development", "DATABASE_URL": self.database_url}
        with patch.dict(os.environ, environment), redirect_stdout(StringIO()):
            exit_code = cli_main(["reset-db", "--no-seed"])

        self.assertEqual(exit_code, 0)
        engine = create_database_engine(self.database_url)
        try:
            with engine.connect() as connection:
                user_count = connection.exec_driver_sql("SELECT COUNT(*) FROM users").scalar_one()
        finally:
            engine.dispose()
        self.assertEqual(user_count, 0)

    def test_reset_cli_seeds_by_default(self) -> None:
        environment = {"APP_ENV": "development", "DATABASE_URL": self.database_url}
        with patch.dict(os.environ, environment), redirect_stdout(StringIO()):
            exit_code = cli_main(["reset-db"])

        self.assertEqual(exit_code, 0)
        engine = create_database_engine(self.database_url)
        try:
            with engine.connect() as connection:
                phone = connection.exec_driver_sql(
                    "SELECT phone_number FROM users WHERE phone_number = ?",
                    (DEMO_CUSTOMER_PHONE,),
                ).scalar_one()
        finally:
            engine.dispose()
        self.assertEqual(phone, DEMO_CUSTOMER_PHONE)

    def test_init_cli_preserves_empty_database_after_no_seed_reset(self) -> None:
        environment = {"APP_ENV": "development", "DATABASE_URL": self.database_url}
        with patch.dict(os.environ, environment), redirect_stdout(StringIO()):
            reset_exit_code = cli_main(["reset-db", "--no-seed"])
            init_exit_code = cli_main(["init-db"])

        self.assertEqual(reset_exit_code, 0)
        self.assertEqual(init_exit_code, 0)
        engine = create_database_engine(self.database_url)
        try:
            with engine.connect() as connection:
                user_count = connection.exec_driver_sql("SELECT COUNT(*) FROM users").scalar_one()
                account_count = connection.exec_driver_sql(
                    "SELECT COUNT(*) FROM accounts"
                ).scalar_one()
        finally:
            engine.dispose()
        self.assertEqual(user_count, 0)
        self.assertEqual(account_count, 0)

    def test_reset_cli_rejects_production_before_creating_database(self) -> None:
        environment = {"APP_ENV": "production", "DATABASE_URL": self.database_url}
        errors = StringIO()
        with patch.dict(os.environ, environment), redirect_stderr(errors):
            exit_code = cli_main(["reset-db"])

        self.assertEqual(exit_code, 2)
        self.assertIn("APP_ENV=development", errors.getvalue())
        self.assertFalse(self.database_path.exists())
