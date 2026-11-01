from sqlalchemy.engine import Connection


def user_by_kakao_subject(connection: Connection, kakao_subject: str) -> dict[str, object] | None:
    row = connection.exec_driver_sql(
        "SELECT id, name, phone_number, kakao_subject, password_hash, age, gender, "
        "marital_status, is_employed, role FROM users WHERE kakao_subject = ?",
        (kakao_subject,),
    ).first()
    return dict(row._mapping) if row else None


def user_by_phone(connection: Connection, phone_number: str) -> dict[str, object] | None:
    row = connection.exec_driver_sql(
        "SELECT id, name, phone_number, kakao_subject, password_hash, age, gender, "
        "marital_status, is_employed, role FROM users WHERE phone_number = ?",
        (phone_number,),
    ).first()
    return dict(row._mapping) if row else None


def user_by_id(connection: Connection, user_id: int) -> dict[str, object] | None:
    row = connection.exec_driver_sql(
        "SELECT id, name, phone_number, kakao_subject, password_hash, age, gender, "
        "marital_status, is_employed, role FROM users WHERE id = ?",
        (user_id,),
    ).first()
    return dict(row._mapping) if row else None


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
    result = connection.exec_driver_sql(
        "INSERT INTO users (name, phone_number, kakao_subject, password_hash, age, gender, "
        "marital_status, is_employed, role) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'customer')",
        (
            name,
            phone_number,
            kakao_subject,
            password_hash,
            age,
            gender,
            marital_status,
            int(is_employed),
        ),
    )
    return int(result.lastrowid)


def set_password(connection: Connection, user_id: int, password_hash: str) -> bool:
    result = connection.exec_driver_sql(
        "UPDATE users SET password_hash = ? WHERE id = ? AND role = 'customer'",
        (password_hash, user_id),
    )
    return result.rowcount == 1
