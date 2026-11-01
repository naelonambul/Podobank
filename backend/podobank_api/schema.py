from sqlalchemy.engine import Connection

SCHEMA_VERSION = 3

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS schema_meta (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        version INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone_number TEXT NOT NULL UNIQUE,
        kakao_subject TEXT UNIQUE,
        password_hash TEXT,
        age INTEGER CHECK (age BETWEEN 1 AND 120),
        gender TEXT CHECK (gender IN ('male', 'female')),
        marital_status TEXT CHECK (marital_status IN ('single', 'married')),
        is_employed INTEGER CHECK (is_employed IN (0, 1)),
        role TEXT NOT NULL CHECK (role IN ('customer', 'bank_employee')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CHECK (
            (role = 'customer' AND age IS NOT NULL AND gender IS NOT NULL
                AND marital_status IS NOT NULL AND is_employed IS NOT NULL)
            OR role = 'bank_employee'
        )
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_user_id INTEGER NOT NULL UNIQUE,
        account_number TEXT NOT NULL UNIQUE,
        balance_krw INTEGER NOT NULL DEFAULT 0 CHECK (balance_krw >= 0),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS transaction_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id TEXT NOT NULL,
        account_id INTEGER NOT NULL,
        entry_type TEXT NOT NULL CHECK (
            entry_type IN ('deposit', 'withdrawal', 'transfer_in', 'transfer_out',
                'loan_disbursement', 'loan_repayment')
        ),
        amount_krw INTEGER NOT NULL CHECK (amount_krw > 0),
        counterparty_account_number TEXT,
        memo TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE RESTRICT
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_transaction_entries_account_created "
    "ON transaction_entries (account_id, created_at DESC, id DESC)",
    """
    CREATE TABLE IF NOT EXISTS loan_products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        principal_krw INTEGER NOT NULL CHECK (principal_krw > 0),
        term_months INTEGER NOT NULL CHECK (term_months > 0),
        monthly_installment_krw INTEGER NOT NULL CHECK (monthly_installment_krw > 0),
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
        CHECK (principal_krw = monthly_installment_krw * term_months)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS loans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        status TEXT NOT NULL CHECK (
            status IN ('pending', 'repaying', 'rejected', 'paid_off')
        ),
        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        decided_at TEXT,
        approved_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT,
        FOREIGN KEY (product_id) REFERENCES loan_products(id) ON DELETE RESTRICT
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_loans_one_active_per_user "
    "ON loans (user_id) WHERE status IN ('pending', 'repaying')",
    "CREATE INDEX IF NOT EXISTS ix_loans_status_applied ON loans (status, applied_at)",
    """
    CREATE TABLE IF NOT EXISTS loan_installments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        loan_id INTEGER NOT NULL,
        installment_number INTEGER NOT NULL CHECK (installment_number > 0),
        due_date TEXT NOT NULL,
        amount_krw INTEGER NOT NULL CHECK (amount_krw > 0),
        status TEXT NOT NULL CHECK (
            status IN ('scheduled', 'processing', 'overdue', 'paid')
        ),
        paid_at TEXT,
        UNIQUE (loan_id, installment_number),
        FOREIGN KEY (loan_id) REFERENCES loans(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_loan_installments_due "
    "ON loan_installments (status, due_date, id)",
)


def create_schema(connection: Connection) -> None:
    for statement in SCHEMA_STATEMENTS:
        connection.exec_driver_sql(statement)
    connection.exec_driver_sql(
        "INSERT INTO schema_meta (id, version) VALUES (1, ?) "
        "ON CONFLICT(id) DO UPDATE SET version = excluded.version",
        (SCHEMA_VERSION,),
    )
