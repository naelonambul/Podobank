import argparse
import os
import sys
from collections.abc import Sequence

from podobank_api.database import (
    DatabaseSafetyError,
    create_database_engine,
    initialize_database,
    reset_database,
    validate_reset_target,
)
from podobank_api.settings import DEFAULT_DATABASE_URL, Settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="podobank-api")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="create the SQLite schema and default sample data")
    commands.add_parser("run-repayment-worker", help="process scheduled loan repayments")

    reset_parser = commands.add_parser(
        "reset-db",
        help="recreate the development SQLite schema and sample data",
    )
    reset_parser.add_argument(
        "--no-seed",
        action="store_true",
        help="create the schema without inserting sample rows",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)

    try:
        if arguments.command == "reset-db":
            app_env = os.environ.get("APP_ENV", "development").strip().lower()
            database_url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL).strip()
            validate_reset_target(app_env, database_url)
        settings = Settings.from_environment()
        if arguments.command == "run-repayment-worker":
            from podobank_api.features.loans.worker import main as worker_main

            worker_main()
            return 0
        if arguments.command == "reset-db":
            validate_reset_target(settings.app_env, settings.database_url)

        engine = create_database_engine(settings.database_url)
        try:
            if arguments.command == "reset-db":
                reset_database(
                    engine,
                    app_env=settings.app_env,
                    include_seed=not arguments.no_seed,
                    staff_initial_phone=settings.staff_initial_phone,
                    staff_initial_password=settings.staff_initial_password,
                )
            else:
                initialize_database(
                    engine,
                    staff_initial_phone=settings.staff_initial_phone,
                    staff_initial_password=settings.staff_initial_password,
                )
        finally:
            engine.dispose()
    except (DatabaseSafetyError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if arguments.command == "reset-db" and arguments.no_seed:
        print("SQLite schema recreated without sample data.")
    else:
        print("SQLite schema is ready with default sample data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
