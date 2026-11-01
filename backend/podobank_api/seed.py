from sqlalchemy.engine import Connection

DEMO_CUSTOMER_PHONE = "01000000001"
DEMO_ACCOUNT_NUMBER = "100000000001"


def seed_default_data(connection: Connection) -> None:
    connection.exec_driver_sql(
        """
        INSERT INTO users (
            name, phone_number, age, gender, marital_status, is_employed, role
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (phone_number) DO NOTHING
        """,
        ("가상 고객 1", DEMO_CUSTOMER_PHONE, 30, "female", "single", 1, "customer"),
    )
    customer_id = connection.exec_driver_sql(
        "SELECT id FROM users WHERE phone_number = ?",
        (DEMO_CUSTOMER_PHONE,),
    ).scalar_one()
    connection.exec_driver_sql(
        """
        INSERT INTO accounts (owner_user_id, account_number, balance)
        VALUES (?, ?, 0)
        ON CONFLICT (account_number) DO NOTHING
        """,
        (customer_id, DEMO_ACCOUNT_NUMBER),
    )
