import argparse
import sys
from collections.abc import Sequence

from podobank_api.database import (
    DatabaseSafetyError,
    create_database_engine,
    initialize_database,
    reset_database,
    validate_reset_target,
)
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)

    try:
        settings = Settings.from_environment()
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
        print(f"error: {error}", file=sys.stderr)
        return 2

    if arguments.command == "reset-db" and arguments.no_seed:
        print("MariaDB schema recreated without sample data.")
    else:
        print("MariaDB schema is ready with default sample data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
