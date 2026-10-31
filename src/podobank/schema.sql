CREATE TABLE IF NOT EXISTS customers (
    customer_id CHAR(36) NOT NULL PRIMARY KEY,
    profile_json JSON NOT NULL,
    created_at DATETIME(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS accounts (
    account_id CHAR(36) NOT NULL PRIMARY KEY,
    customer_id CHAR(36) NOT NULL,
    balance_won BIGINT UNSIGNED NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'KRW',
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_accounts_customer FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id),
    INDEX idx_accounts_customer (customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS merchants (
    merchant_id CHAR(36) NOT NULL PRIMARY KEY,
    partner_id VARCHAR(64) NOT NULL,
    display_name VARCHAR(160) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    INDEX idx_merchants_partner (partner_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS loan_product_snapshots (
    snapshot_id CHAR(36) NOT NULL PRIMARY KEY,
    product_ref VARCHAR(160) NOT NULL,
    institution_name VARCHAR(160) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    product_category VARCHAR(64) NOT NULL,
    facts_json JSON NOT NULL,
    source_url TEXT NOT NULL,
    retrieved_at DATETIME(6) NOT NULL,
    effective_date DATE NULL,
    source_status VARCHAR(32) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    INDEX idx_snapshots_product_time (product_ref, retrieved_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS loans (
    loan_id CHAR(36) NOT NULL PRIMARY KEY,
    customer_id CHAR(36) NOT NULL,
    account_id CHAR(36) NOT NULL,
    snapshot_id CHAR(36) NULL,
    amount_won BIGINT UNSIGNED NOT NULL,
    term_months SMALLINT UNSIGNED NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_loans_customer FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id),
    CONSTRAINT fk_loans_account FOREIGN KEY (account_id)
        REFERENCES accounts (account_id),
    CONSTRAINT fk_loans_snapshot FOREIGN KEY (snapshot_id)
        REFERENCES loan_product_snapshots (snapshot_id),
    INDEX idx_loans_customer (customer_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS payments (
    payment_id CHAR(36) NOT NULL PRIMARY KEY,
    partner_id VARCHAR(64) NOT NULL,
    merchant_id CHAR(36) NOT NULL,
    payer_account_id CHAR(36) NOT NULL,
    amount_won BIGINT UNSIGNED NOT NULL,
    status VARCHAR(32) NOT NULL,
    correlation_id CHAR(36) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_payments_merchant FOREIGN KEY (merchant_id)
        REFERENCES merchants (merchant_id),
    CONSTRAINT fk_payments_account FOREIGN KEY (payer_account_id)
        REFERENCES accounts (account_id),
    INDEX idx_payments_partner (partner_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS idempotency_records (
    record_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    partner_id VARCHAR(64) NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    request_hash CHAR(64) NOT NULL,
    response_json JSON NULL,
    created_at DATETIME(6) NOT NULL,
    UNIQUE KEY uq_idempotency_partner_key (partner_id, idempotency_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS catalog_refresh_state (
    institution_id VARCHAR(64) NOT NULL PRIMARY KEY,
    lease_owner VARCHAR(128) NULL,
    lease_expires_at DATETIME(6) NULL,
    last_started_at DATETIME(6) NULL,
    last_completed_at DATETIME(6) NULL,
    last_error VARCHAR(500) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS event_sequence_state (
    singleton_id TINYINT UNSIGNED NOT NULL PRIMARY KEY,
    last_sequence BIGINT UNSIGNED NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS domain_events (
    sequence BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    event_id CHAR(36) NOT NULL,
    schema_version SMALLINT UNSIGNED NOT NULL,
    event_type VARCHAR(96) NOT NULL,
    occurred_at DATETIME(6) NOT NULL,
    recorded_at DATETIME(6) NOT NULL,
    correlation_id CHAR(36) NOT NULL,
    entity_refs JSON NOT NULL,
    data JSON NOT NULL,
    UNIQUE KEY uq_domain_events_event_id (event_id),
    INDEX idx_domain_events_correlation (correlation_id, sequence),
    INDEX idx_domain_events_type_sequence (event_type, sequence)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS telemetry_outbox (
    event_id CHAR(36) NOT NULL PRIMARY KEY,
    created_at DATETIME(6) NOT NULL,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    lease_owner VARCHAR(128) NULL,
    lease_expires_at DATETIME(6) NULL,
    delivered_at DATETIME(6) NULL,
    CONSTRAINT fk_outbox_event FOREIGN KEY (event_id)
        REFERENCES domain_events (event_id),
    INDEX idx_outbox_pending (delivered_at, lease_expires_at, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
