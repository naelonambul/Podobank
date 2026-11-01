from sqlalchemy.engine import Connection

DEMO_CUSTOMER_PHONE = "01000000001"
DEMO_ACCOUNT_NUMBER = "100000000001"
DEMO_STAFF_PHONE = "01099990000"

DEMO_CUSTOMERS = (
    (DEMO_CUSTOMER_PHONE, DEMO_ACCOUNT_NUMBER, "김포도", 30, "female", "single", 1),
    ("01000000002", "100000000002", "이포도", 26, "male", "married", 1),
    ("01000000003", "100000000003", "김포도", 41, "female", "married", 0),
)
LOAN_PRODUCTS = (
    ("car_purchase", "자동차 구매", 30_000_000, 60, 500_000),
    ("jeonse", "전세자금", 96_000_000, 24, 4_000_000),
    ("home_purchase", "주택 매매", 360_000_000, 360, 1_000_000),
)


def seed_default_data(
    connection: Connection,
    *,
    staff_initial_phone: str = DEMO_STAFF_PHONE,
    staff_initial_password: str = "",
) -> None:
    from podobank_api.features.auth.service import hash_password

    for phone, account_number, name, age, gender, marital_status, is_employed in DEMO_CUSTOMERS:
        connection.exec_driver_sql(
            """
            INSERT INTO users (
                name, phone_number, age, gender, marital_status, is_employed, role
            ) VALUES (?, ?, ?, ?, ?, ?, 'customer')
            ON CONFLICT (phone_number) DO NOTHING
            """,
            (name, phone, age, gender, marital_status, is_employed),
        )
        customer_id = connection.exec_driver_sql(
            "SELECT id FROM users WHERE phone_number = ?",
            (phone,),
        ).scalar_one()
        connection.exec_driver_sql(
            """
            INSERT INTO accounts (owner_user_id, account_number, balance_krw)
            VALUES (?, ?, 0)
            ON CONFLICT (owner_user_id) DO NOTHING
            """,
            (customer_id, account_number),
        )

    password_hash = hash_password(staff_initial_password) if staff_initial_password else None
    connection.exec_driver_sql(
        """
        INSERT INTO users (name, phone_number, password_hash, role)
        VALUES ('포도은행 직원', ?, ?, 'bank_employee')
        ON CONFLICT (phone_number) DO NOTHING
        """,
        (staff_initial_phone, password_hash),
    )
    for product_code, name, principal_krw, term_months, monthly_installment_krw in LOAN_PRODUCTS:
        connection.exec_driver_sql(
            "INSERT INTO loan_products (product_code, name, principal_krw, term_months, "
            "monthly_installment_krw) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (product_code) DO NOTHING",
            (product_code, name, principal_krw, term_months, monthly_installment_krw),
        )
