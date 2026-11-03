from sqlalchemy import text
from sqlalchemy.engine import Connection

from podobank_api.features.auth.passwords import hash_password
from podobank_api.seed import DEMO_CUSTOMER_PHONE


def rotate_demo_credentials(
    connection: Connection,
    *,
    employee_phone: str,
    employee_password: str,
    demo_customer_password: str,
) -> None:
    """Update credentials for the configured employee and fixed demo customer only."""
    targets = (
        (employee_phone, "bank_employee"),
        (DEMO_CUSTOMER_PHONE, "customer"),
    )
    for phone_number, expected_role in targets:
        user = connection.execute(
            text("SELECT role FROM users WHERE phone_number = :phone_number"),
            {"phone_number": phone_number},
        ).one_or_none()
        if user is None or user.role != expected_role:
            raise ValueError("demo credential target is missing or has an unexpected role")

    employee_hash = hash_password(employee_password)
    customer_hash = hash_password(demo_customer_password)
    for phone_number, expected_role, password_hash in (
        (employee_phone, "bank_employee", employee_hash),
        (DEMO_CUSTOMER_PHONE, "customer", customer_hash),
    ):
        result = connection.execute(
            text(
                "UPDATE users SET password_hash = :password_hash "
                "WHERE phone_number = :phone_number AND role = :role"
            ),
            {
                "password_hash": password_hash,
                "phone_number": phone_number,
                "role": expected_role,
            },
        )
        if result.rowcount != 1:
            raise ValueError("demo credential target changed during the update")
