from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url

from podobank_api.schema import create_schema
from podobank_api.seed import seed_default_data


class DatabaseSafetyError(RuntimeError):
    """Raised when a database operation is unsafe for the selected environment."""


def database_backend(database_url: str) -> str:
    return make_url(database_url).get_backend_name()


def validate_reset_target(app_env: str, database_url: str) -> None:
    url = make_url(database_url)
    if url.drivername != "mysql+pymysql":
        raise DatabaseSafetyError("database commands require the mysql+pymysql driver")

    expected_databases = {"development": "podobank_dev", "test": "podobank_test"}
    expected_database = expected_databases.get(app_env)
    if expected_database is None:
        raise DatabaseSafetyError(
            "reset-db is allowed only for APP_ENV=development or APP_ENV=test"
        )
    if url.database != expected_database:
        raise DatabaseSafetyError(
            f"reset-db is restricted to the {expected_database} database for APP_ENV={app_env}"
        )
    if url.host not in {"db", "localhost", "127.0.0.1"}:
        raise DatabaseSafetyError("reset-db is restricted to a local MariaDB service")
    if url.port not in {None, 3306}:
        raise DatabaseSafetyError("reset-db is restricted to the local MariaDB port 3306")


def create_database_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    if url.drivername != "mysql+pymysql":
        raise DatabaseSafetyError("the backend requires a mysql+pymysql MariaDB URL")

    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


def initialize_database(engine: Engine, *, include_seed: bool = True) -> None:
    if engine.dialect.name != "mysql" or engine.dialect.driver != "pymysql":
        raise DatabaseSafetyError("the backend requires a MariaDB connection using PyMySQL")

    with engine.connect() as connection:
        existing_table_count = connection.execute(
            text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()")
        ).scalar_one()
        connection.commit()

        create_schema(connection)
        connection.commit()

        if include_seed and existing_table_count == 0:
            with connection.begin():
                seed_default_data(connection)


def reset_database(
    engine: Engine,
    *,
    app_env: str,
    include_seed: bool = True,
) -> None:
    validate_reset_target(app_env, str(engine.url))

    with engine.connect() as connection:
        connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 0")
        connection.commit()
        try:
            database_objects = connection.execute(
                text(
                    "SELECT table_type, table_name FROM information_schema.tables "
                    "WHERE table_schema = DATABASE() "
                    "ORDER BY CASE table_type WHEN 'VIEW' THEN 0 ELSE 1 END, table_name"
                )
            ).all()
            connection.commit()

            preparer = connection.dialect.identifier_preparer
            for object_type, object_name in database_objects:
                quoted_name = preparer.quote(object_name)
                drop_kind = "VIEW" if object_type == "VIEW" else "TABLE"
                connection.exec_driver_sql(f"DROP {drop_kind} IF EXISTS {quoted_name}")
                connection.commit()

            create_schema(connection)
            connection.commit()

            if include_seed:
                with connection.begin():
                    seed_default_data(connection)
        finally:
            if connection.in_transaction():
                connection.rollback()
            connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 1")
            connection.commit()
