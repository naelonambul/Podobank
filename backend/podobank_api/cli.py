import argparse
import os
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

from podobank_api.database import (
    DatabaseSafetyError,
    create_database_engine,
    initialize_database,
    reset_database,
    validate_demo_seed_target,
    validate_reset_target,
)
from podobank_api.demo_credentials import rotate_demo_credentials
from podobank_api.demo_seed import DemoSeedSummary, seed_demo_data
from podobank_api.features.loans.service import LoanService
from podobank_api.features.observability.events import configure_financial_event_logging
from podobank_api.seed import DEMO_ACCOUNT_NUMBER, DEMO_CUSTOMER_PHONE, LOAN_PRODUCTS
from podobank_api.settings import Settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="podobank-api")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="create the MariaDB schema and default sample data")
    commands.add_parser(
        "seed-demo-data",
        help="insert the large local development sample dataset",
    )
    commands.add_parser(
        "set-demo-credentials",
        help="set non-default passwords for the local demo employee and customer",
    )

    reset_parser = commands.add_parser(
        "reset-db",
        help="recreate the explicitly allowed development database schema and sample data",
    )
    reset_parser.add_argument(
        "--no-seed",
        action="store_true",
        help="create the schema without inserting sample rows",
    )
    repayments_parser = commands.add_parser(
        "process-repayments",
        help="process due loan installments once; schedule this command externally",
    )
    repayments_parser.add_argument(
        "--as-of-date",
        type=_parse_iso_date,
        help="UTC processing date in YYYY-MM-DD format (defaults to today)",
    )
    return parser


def _require_initialized_default_seed(connection: Connection, settings: Settings) -> None:
    expected_tables = {
        "users",
        "accounts",
        "ledger_entries",
        "loan_products",
        "loan_applications",
        "loan_repayments",
    }
    existing_tables = set(
        connection.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'"
            )
        ).scalars()
    )
    if not expected_tables.issubset(existing_tables):
        raise ValueError("run podobank-api init-db before seed-demo-data")

    demo_seed_exists = connection.execute(
        text(
            "SELECT 1 FROM users AS u JOIN accounts AS a ON a.owner_user_id = u.id "
            "WHERE u.phone_number = :phone_number AND u.role = 'customer' "
            "AND a.account_number = :account_number"
        ),
        {
            "phone_number": DEMO_CUSTOMER_PHONE,
            "account_number": DEMO_ACCOUNT_NUMBER,
        },
    ).first()
    employee_exists = connection.execute(
        text("SELECT 1 FROM users WHERE phone_number = :phone_number AND role = 'bank_employee'"),
        {"phone_number": settings.bank_employee_phone},
    ).first()
    loan_product_codes = {
        str(row[0])
        for row in connection.execute(
            text("SELECT code FROM loan_products WHERE code IN :codes").bindparams(
                bindparam("codes", expanding=True)
            ),
            {"codes": [product["code"] for product in LOAN_PRODUCTS]},
        ).all()
    }
    if (
        demo_seed_exists is None
        or employee_exists is None
        or loan_product_codes != {str(product["code"]) for product in LOAN_PRODUCTS}
    ):
        raise ValueError("run podobank-api init-db before seed-demo-data")


def _parse_iso_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format") from error
    if parsed.isoformat() != value:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format")
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)

    try:
        settings = Settings.from_environment()
        if arguments.command == "process-repayments":
            configure_financial_event_logging(
                os.environ.get("FINANCIAL_EVENTS_PATH"),
                wait_on_exit=False,
            )
            engine = create_database_engine(settings.database_url)
            try:
                service = LoanService(engine)
                as_of_date = arguments.as_of_date or datetime.now(UTC).date()
                result = service.process_due_repayments(as_of_date=as_of_date)
            finally:
                engine.dispose()
            print(
                "Repayment processing completed: "
                f"processed={result.processed} paid={result.paid} "
                f"overdue={result.overdue} skipped={result.skipped}"
            )
            return 0
        if arguments.command == "set-demo-credentials":
            validate_demo_seed_target(settings.app_env, settings.database_url)
            settings.validate_employee_seed()
            settings.validate_demo_customer_seed()
            if settings.bank_employee_password == "local-demo-employee-password":
                raise ValueError("BANK_EMPLOYEE_PASSWORD must not use the local default")
            if settings.demo_customer_password == "local-demo-customer-password":
                raise ValueError("DEMO_CUSTOMER_PASSWORD must not use the local default")
            engine = create_database_engine(settings.database_url)
            try:
                with engine.begin() as connection:
                    rotate_demo_credentials(
                        connection,
                        employee_phone=settings.bank_employee_phone,
                        employee_password=settings.bank_employee_password,
                        demo_customer_password=settings.demo_customer_password,
                    )
            finally:
                engine.dispose()
            print("Demo employee and customer credentials updated.")
            return 0
        if arguments.command == "seed-demo-data":
            validate_demo_seed_target(settings.app_env, settings.database_url)
            settings.validate_demo_customer_seed()
            engine = create_database_engine(settings.database_url)
            try:
                with engine.begin() as connection:
                    _require_initialized_default_seed(connection, settings)
                    summary: DemoSeedSummary = seed_demo_data(
                        connection,
                        demo_customer_password=settings.demo_customer_password,
                    )
            finally:
                engine.dispose()
            action = "already present" if summary.already_present else "seeded"
            print(
                f"Demo sample data {action}: customers={summary.customer_count} "
                f"accounts={summary.account_count} ledger_entries={summary.ledger_entry_count} "
                f"loan_applications={summary.loan_application_count} "
                f"repayments={summary.repayment_count}"
            )
            return 0
        if arguments.command == "reset-db":
            validate_reset_target(settings.app_env, settings.database_url)
            include_seed = not arguments.no_seed
        else:
            include_seed = settings.app_env != "production"
        if include_seed:
            settings.validate_employee_seed()

        engine = create_database_engine(settings.database_url)
        try:
            if arguments.command == "reset-db":
                reset_database(
                    engine,
                    app_env=settings.app_env,
                    include_seed=include_seed,
                    employee_phone=settings.bank_employee_phone,
                    employee_password=settings.bank_employee_password,
                )
            else:
                initialize_database(
                    engine,
                    include_seed=include_seed,
                    employee_phone=settings.bank_employee_phone,
                    employee_password=settings.bank_employee_password,
                )
        finally:
            engine.dispose()
    except (DatabaseSafetyError, ValueError) as error:
        if arguments.command == "process-repayments":
            print("error: repayment processing failed", file=sys.stderr)
            return 1
        print(f"error: {error}", file=sys.stderr)
        return 2
    except DBAPIError:
        if arguments.command == "process-repayments":
            print("error: repayment processing failed", file=sys.stderr)
            return 1
        raise
    except Exception:
        if arguments.command == "process-repayments":
            print("error: repayment processing failed", file=sys.stderr)
            return 1
        raise

    if arguments.command == "reset-db" and arguments.no_seed:
        print("MariaDB schema recreated without sample data.")
    else:
        print("MariaDB schema is ready with default sample data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
