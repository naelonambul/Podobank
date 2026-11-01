from sqlalchemy import text
from sqlalchemy.engine import Connection

DEMO_CUSTOMER_PHONE = "01000000001"
DEMO_ACCOUNT_NUMBER = "100000000001"


def seed_default_data(connection: Connection) -> None:
    connection.execute(
        text(
            """
        INSERT INTO users (
            name, phone_number, age, gender, marital_status, is_employed, role
        ) VALUES (
            :name, :phone_number, :age, :gender, :marital_status, :is_employed, :role
        )
        ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)
        """
        ),
        {
            "name": "가상 고객 1",
            "phone_number": DEMO_CUSTOMER_PHONE,
            "age": 30,
            "gender": "female",
            "marital_status": "single",
            "is_employed": 1,
            "role": "customer",
        },
    )
    customer_id = connection.execute(
        text("SELECT id FROM users WHERE phone_number = :phone_number"),
        {"phone_number": DEMO_CUSTOMER_PHONE},
    ).scalar_one()
    connection.execute(
        text(
            """
            INSERT INTO accounts (owner_user_id, account_number, balance)
            VALUES (:owner_user_id, :account_number, 0)
            ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)
            """
        ),
        {"owner_user_id": customer_id, "account_number": DEMO_ACCOUNT_NUMBER},
    )
