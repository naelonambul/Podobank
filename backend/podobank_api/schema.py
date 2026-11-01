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
)


def create_schema(connection: Connection) -> None:
    for statement in SCHEMA_STATEMENTS:
        connection.exec_driver_sql(statement)
