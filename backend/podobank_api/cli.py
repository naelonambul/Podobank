import argparse
import os
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime

from sqlalchemy.exc import DBAPIError

from podobank_api.database import (
    DatabaseSafetyError,
    create_database_engine,
    initialize_database,
    reset_database,
    validate_reset_target,
)
from podobank_api.features.loans.service import LoanService
from podobank_api.features.observability.events import configure_financial_event_logging
from podobank_api.settings import Settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="podobank-api")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="create the MariaDB schema and default sample data")

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
