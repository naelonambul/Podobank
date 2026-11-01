from datetime import UTC, datetime

from sqlalchemy.engine import Connection

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS users (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        name VARCHAR(120) NOT NULL,
        phone_number VARCHAR(20) NOT NULL,
        kakao_subject VARCHAR(191) NULL,
        password_hash VARCHAR(255) NULL,
        age TINYINT UNSIGNED NOT NULL,
        gender VARCHAR(16) NOT NULL,
        marital_status VARCHAR(16) NOT NULL,
        is_employed TINYINT(1) NOT NULL,
        role VARCHAR(24) NOT NULL,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        PRIMARY KEY (id),
        CONSTRAINT uq_users_phone_number UNIQUE (phone_number),
        CONSTRAINT uq_users_kakao_subject UNIQUE (kakao_subject),
        CONSTRAINT chk_users_age CHECK (age BETWEEN 1 AND 120),
        CONSTRAINT chk_users_gender CHECK (gender IN ('male', 'female')),
        CONSTRAINT chk_users_marital_status CHECK (marital_status IN ('single', 'married')),
        CONSTRAINT chk_users_is_employed CHECK (is_employed IN (0, 1)),
        CONSTRAINT chk_users_role CHECK (role IN ('customer', 'bank_employee'))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS accounts (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        owner_user_id BIGINT UNSIGNED NOT NULL,
        account_number VARCHAR(32) NOT NULL,
        balance BIGINT NOT NULL DEFAULT 0,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        PRIMARY KEY (id),
        CONSTRAINT uq_accounts_owner_user_id UNIQUE (owner_user_id),
        CONSTRAINT uq_accounts_account_number UNIQUE (account_number),
        CONSTRAINT chk_accounts_balance CHECK (balance >= 0),
        CONSTRAINT fk_accounts_owner_user_id FOREIGN KEY (owner_user_id)
            REFERENCES users (id) ON DELETE RESTRICT
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS loan_products (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        code VARCHAR(32) NOT NULL,
        name VARCHAR(120) NOT NULL,
        principal_amount BIGINT NOT NULL,
        term_months SMALLINT UNSIGNED NOT NULL,
        monthly_installment BIGINT NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_loan_products_code UNIQUE (code),
        CONSTRAINT chk_loan_products_terms CHECK (
            principal_amount > 0 AND term_months > 0 AND monthly_installment > 0
            AND principal_amount = monthly_installment * term_months
        )
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS loan_applications (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        user_id BIGINT UNSIGNED NOT NULL,
        product_id BIGINT UNSIGNED NOT NULL,
        product_code VARCHAR(32) NOT NULL,
        product_name VARCHAR(120) NOT NULL,
        principal_amount BIGINT NOT NULL,
        term_months SMALLINT UNSIGNED NOT NULL,
        monthly_installment BIGINT NOT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'pending',
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        reviewed_at DATETIME(6) NULL,
        reviewed_by BIGINT UNSIGNED NULL,
        approved_at DATETIME(6) NULL,
        PRIMARY KEY (id),
        KEY ix_loan_applications_user_status_id (user_id, status, id),
        KEY ix_loan_applications_status_id (status, id),
        CONSTRAINT chk_loan_applications_status CHECK (
            status IN ('pending', 'repaying', 'rejected', 'repaid')
        ),
        CONSTRAINT chk_loan_applications_terms CHECK (
            principal_amount > 0 AND term_months > 0 AND monthly_installment > 0
            AND principal_amount = monthly_installment * term_months
        ),
        CONSTRAINT fk_loan_applications_user FOREIGN KEY (user_id)
            REFERENCES users (id) ON DELETE RESTRICT,
        CONSTRAINT fk_loan_applications_product FOREIGN KEY (product_id)
            REFERENCES loan_products (id) ON DELETE RESTRICT,
        CONSTRAINT fk_loan_applications_reviewer FOREIGN KEY (reviewed_by)
            REFERENCES users (id) ON DELETE RESTRICT
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS loan_repayments (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        loan_application_id BIGINT UNSIGNED NOT NULL,
        installment_number SMALLINT UNSIGNED NOT NULL,
        due_date DATE NOT NULL,
        amount BIGINT NOT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'scheduled',
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        processed_at DATETIME(6) NULL,
        paid_at DATETIME(6) NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_loan_repayments_installment
            UNIQUE (loan_application_id, installment_number),
        KEY ix_loan_repayments_due_status (
            status, due_date, loan_application_id, installment_number
        ),
        CONSTRAINT chk_loan_repayments_installment CHECK (
            installment_number > 0 AND amount > 0
        ),
        CONSTRAINT chk_loan_repayments_status CHECK (
            status IN ('scheduled', 'paid', 'overdue')
        ),
        CONSTRAINT fk_loan_repayments_application FOREIGN KEY (loan_application_id)
            REFERENCES loan_applications (id) ON DELETE RESTRICT
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
)


def ledger_schema_statement(now: datetime | None = None) -> str:
    current = now or datetime.now(UTC)
    current_month = datetime(current.year, current.month, 1)
    partitions = [
        "PARTITION p_before_{month} VALUES LESS THAN ('{boundary}')".format(
            month=current_month.strftime("%Y%m"),
            boundary=current_month.strftime("%Y-%m-%d"),
        )
    ]

    for offset in range(12):
        year = current_month.year + (current_month.month - 1 + offset) // 12
        month = (current_month.month - 1 + offset) % 12 + 1
        next_year = year + (month == 12)
        next_month = month % 12 + 1
        boundary = datetime(next_year, next_month, 1)
        partitions.append(
            "PARTITION p_{month} VALUES LESS THAN ('{boundary}')".format(
                month=f"{year:04d}{month:02d}",
                boundary=boundary.strftime("%Y-%m-%d"),
            )
        )

    partitions.append("PARTITION p_future VALUES LESS THAN (MAXVALUE)")
    partition_sql = ",\n        ".join(partitions)
    return f"""
    CREATE TABLE IF NOT EXISTS ledger_entries (
        entry_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        posted_at DATETIME(6) NOT NULL,
        transaction_id CHAR(36) NOT NULL,
        account_id BIGINT UNSIGNED NOT NULL,
        user_id BIGINT UNSIGNED NOT NULL,
        entry_type VARCHAR(24) NOT NULL,
        amount BIGINT NOT NULL,
        PRIMARY KEY (entry_id, posted_at),
        KEY ix_ledger_account_posted_entry (account_id, posted_at, entry_id),
        KEY ix_ledger_transaction_posted_entry (transaction_id, posted_at, entry_id),
        CONSTRAINT chk_ledger_entry_type CHECK (
            entry_type IN (
                'deposit', 'withdrawal', 'transfer_in', 'transfer_out',
                'loan_disbursement', 'loan_repayment'
            )
        ),
        CONSTRAINT chk_ledger_amount CHECK (amount <> 0)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    PARTITION BY RANGE COLUMNS (posted_at) (
        {partition_sql}
    )
    """


def create_schema(connection: Connection) -> None:
    for statement in SCHEMA_STATEMENTS:
        connection.exec_driver_sql(statement)
    connection.exec_driver_sql(ledger_schema_statement())
