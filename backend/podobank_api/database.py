from pathlib import Path

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.engine.url import make_url

from podobank_api.schema import SCHEMA_VERSION, create_schema
from podobank_api.seed import seed_default_data


class DatabaseSafetyError(RuntimeError):
    """Raised when a database operation is unsafe for the selected environment."""


def get_engine(request: Request) -> Engine:
    return request.app.state.engine


def database_backend(database_url: str) -> str:
    return make_url(database_url).get_backend_name()


def validate_reset_target(app_env: str, database_url: str) -> None:
    if app_env != "development":
        raise DatabaseSafetyError("reset-db is allowed only when APP_ENV=development")
    if database_backend(database_url) != "sqlite":
        raise DatabaseSafetyError("reset-db is allowed only for a SQLite database")


def create_database_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        raise DatabaseSafetyError("this backend setup currently supports SQLite only")

    database_path = url.database
    if database_path and database_path != ":memory:" and not database_path.startswith("file:"):
        Path(database_path).expanduser().parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


def initialize_database(
    engine: Engine,
    *,
    include_seed: bool = True,
    staff_initial_phone: str = "01099990000",
    staff_initial_password: str = "",
) -> None:
    if engine.dialect.name != "sqlite":
        raise DatabaseSafetyError("this backend setup currently supports SQLite only")

    with engine.begin() as connection:
        existing_table_count = connection.exec_driver_sql(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).scalar_one()
        if existing_table_count:
            has_meta = connection.exec_driver_sql(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_meta'"
            ).first()
            if not has_meta:
                raise DatabaseSafetyError("SQLite schema is outdated; run reset-db in development")
            schema_version = connection.exec_driver_sql(
                "SELECT version FROM schema_meta WHERE id = 1"
            ).scalar_one_or_none()
            if schema_version != SCHEMA_VERSION:
                raise DatabaseSafetyError(
                    "SQLite schema version changed; run reset-db in development"
                )
        create_schema(connection)
        if include_seed and existing_table_count == 0:
            seed_default_data(
                connection,
                staff_initial_phone=staff_initial_phone,
                staff_initial_password=staff_initial_password,
            )


def reset_database(
    engine: Engine,
    *,
    app_env: str,
    include_seed: bool = True,
    staff_initial_phone: str = "01099990000",
    staff_initial_password: str = "",
) -> None:
    validate_reset_target(app_env, str(engine.url))
    connection: Connection

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
        connection.commit()
        try:
            with connection.begin():
                database_objects = connection.exec_driver_sql(
                    "SELECT type, name FROM sqlite_master "
                    "WHERE type IN ('view', 'table') AND name NOT LIKE 'sqlite_%' "
                    "ORDER BY CASE type WHEN 'view' THEN 0 ELSE 1 END"
                ).all()
                preparer = connection.dialect.identifier_preparer
                for object_type, object_name in database_objects:
                    quoted_name = preparer.quote(object_name)
                    connection.exec_driver_sql(
                        f"DROP {object_type.upper()} IF EXISTS {quoted_name}"
                    )

                create_schema(connection)
                if include_seed:
                    seed_default_data(
                        connection,
                        staff_initial_phone=staff_initial_phone,
                        staff_initial_password=staff_initial_password,
                    )
        finally:
            if connection.in_transaction():
                connection.rollback()
            with connection.begin():
                connection.exec_driver_sql("PRAGMA foreign_keys = ON")
