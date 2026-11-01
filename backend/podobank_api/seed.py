from sqlalchemy import text
from sqlalchemy.engine import Connection

from podobank_api.features.auth.passwords import hash_password

DEMO_CUSTOMER_PHONE = "01000000001"
DEMO_ACCOUNT_NUMBER = "100000000001"


def seed_default_data(
    connection: Connection,
    *,
    employee_phone: str,
    employee_password: str,
) -> None:
    if not employee_phone or len(employee_password) < 8:
        raise ValueError("valid bank employee seed credentials are required")

    employee = (
        connection.execute(
            text("SELECT id, role, password_hash FROM users WHERE phone_number = :phone_number"),
            {"phone_number": employee_phone},
        )
        .mappings()
        .one_or_none()
    )
    if employee is None:
        connection.execute(
            text(
                """
                INSERT INTO users (
                    name, phone_number, password_hash, age, gender, marital_status,
                    is_employed, role
                ) VALUES (
                    :name, :phone_number, :password_hash, 35, 'male', 'married', 1,
                    'bank_employee'
                )
                """
            ),
            {
                "name": "은행 직원",
                "phone_number": employee_phone,
                "password_hash": hash_password(employee_password),
            },
        )
    else:
        if employee["role"] != "bank_employee":
            raise ValueError("BANK_EMPLOYEE_PHONE is already used by a non-employee account")
        if employee["password_hash"] is None:
            connection.execute(
                text("UPDATE users SET password_hash = :password_hash WHERE id = :user_id"),
                {
                    "password_hash": hash_password(employee_password),
                    "user_id": employee["id"],
                },
            )

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
