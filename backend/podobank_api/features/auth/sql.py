from sqlalchemy import text
from sqlalchemy.engine import Connection

USER_COLUMNS = "id, name, phone_number, password_hash, kakao_subject, role"


def find_user_by_id(connection: Connection, user_id: int) -> dict[str, object] | None:
    row = (
        connection.execute(
            text(f"SELECT {USER_COLUMNS} FROM users WHERE id = :user_id"),
            {"user_id": user_id},
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


def find_user_by_phone(connection: Connection, phone_number: str) -> dict[str, object] | None:
    row = (
        connection.execute(
            text(f"SELECT {USER_COLUMNS} FROM users WHERE phone_number = :phone_number"),
            {"phone_number": phone_number},
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


def find_user_by_kakao_subject(connection: Connection, subject: str) -> dict[str, object] | None:
    row = (
        connection.execute(
            text(f"SELECT {USER_COLUMNS} FROM users WHERE kakao_subject = :subject"),
            {"subject": subject},
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


def insert_customer(
    connection: Connection,
    *,
    name: str,
    phone_number: str,
    kakao_subject: str,
    password_hash: str | None,
    age: int,
    gender: str,
    marital_status: str,
    is_employed: bool,
) -> int:
    result = connection.execute(
        text(
            """
            INSERT INTO users (
                name, phone_number, kakao_subject, password_hash, age, gender,
                marital_status, is_employed, role
            ) VALUES (
                :name, :phone_number, :kakao_subject, :password_hash, :age, :gender,
                :marital_status, :is_employed, 'customer'
            )
            """
        ),
        {
            "name": name,
            "phone_number": phone_number,
            "kakao_subject": kakao_subject,
            "password_hash": password_hash,
            "age": age,
            "gender": gender,
            "marital_status": marital_status,
            "is_employed": is_employed,
        },
    )
    if result.lastrowid is None:
        raise RuntimeError("MariaDB did not return the new user ID")
    return int(result.lastrowid)


def set_password_if_unset(connection: Connection, *, user_id: int, password_hash: str) -> int:
    result = connection.execute(
        text(
            "UPDATE users SET password_hash = :password_hash "
            "WHERE id = :user_id AND role = 'customer' AND password_hash IS NULL"
        ),
        {"user_id": user_id, "password_hash": password_hash},
    )
    return result.rowcount
