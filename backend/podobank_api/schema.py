from sqlalchemy.engine import Connection

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone_number TEXT NOT NULL UNIQUE,
        age INTEGER NOT NULL CHECK (age BETWEEN 1 AND 120),
        gender TEXT NOT NULL CHECK (gender IN ('male', 'female')),
        marital_status TEXT NOT NULL CHECK (marital_status IN ('single', 'married')),
        is_employed INTEGER NOT NULL CHECK (is_employed IN (0, 1)),
        role TEXT NOT NULL CHECK (role IN ('customer', 'bank_employee')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_user_id INTEGER NOT NULL UNIQUE,
        account_number TEXT NOT NULL UNIQUE,
        balance INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE RESTRICT
    )
    """,
)


def create_schema(connection: Connection) -> None:
    for statement in SCHEMA_STATEMENTS:
        connection.exec_driver_sql(statement)
