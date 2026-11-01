from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection


def list_products(connection: Connection) -> list[dict[str, object]]:
    rows = connection.execute(
        text(
            "SELECT id, code, name, principal_amount, term_months, monthly_installment "
            "FROM loan_products ORDER BY id"
        )
    ).mappings()
    return [dict(row) for row in rows]


def find_product(connection: Connection, product_id: int) -> dict[str, object] | None:
    row = (
        connection.execute(
            text(
                "SELECT id, code, name, principal_amount, term_months, monthly_installment "
                "FROM loan_products WHERE id = :product_id"
            ),
            {"product_id": product_id},
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


def has_active_application(connection: Connection, user_id: int) -> bool:
    return (
        connection.execute(
            text(
                "SELECT 1 FROM loan_applications WHERE user_id = :user_id "
                "AND status IN ('pending', 'repaying') LIMIT 1"
            ),
            {"user_id": user_id},
        ).first()
        is not None
    )


def insert_application(
    connection: Connection,
    *,
    user_id: int,
    product: dict[str, object],
) -> int:
    result = connection.execute(
        text(
            "INSERT INTO loan_applications "
            "(user_id, product_id, product_code, product_name, principal_amount, "
            "term_months, monthly_installment, status) "
            "VALUES (:user_id, :product_id, :product_code, :product_name, :principal_amount, "
            ":term_months, :monthly_installment, 'pending')"
        ),
        {
            "user_id": user_id,
            "product_id": product["id"],
            "product_code": product["code"],
            "product_name": product["name"],
            "principal_amount": product["principal_amount"],
            "term_months": product["term_months"],
            "monthly_installment": product["monthly_installment"],
        },
    )
    if result.lastrowid is None:
        raise RuntimeError("MariaDB did not return the new loan application ID")
    return int(result.lastrowid)


def lock_application(connection: Connection, application_id: int) -> dict[str, object] | None:
    row = (
        connection.execute(
            text(
                "SELECT id, user_id, product_id, product_code, product_name, principal_amount, "
                "term_months, monthly_installment, status, created_at, reviewed_at, reviewed_by, "
                "approved_at FROM loan_applications WHERE id = :application_id "
                "FOR UPDATE WAIT 3"
            ),
            {"application_id": application_id},
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


def find_application(connection: Connection, application_id: int) -> dict[str, object] | None:
    row = (
        connection.execute(
            text(
                "SELECT id, user_id, product_id, product_code, product_name, principal_amount, "
                "term_months, monthly_installment, status, created_at, reviewed_at, reviewed_by, "
                "approved_at FROM loan_applications WHERE id = :application_id"
            ),
            {"application_id": application_id},
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


def update_application_review(
    connection: Connection,
    *,
    application_id: int,
    status: str,
    reviewed_by: int,
    reviewed_at: datetime,
    approved_at: datetime | None,
) -> None:
    result = connection.execute(
        text(
            "UPDATE loan_applications SET status = :status, reviewed_by = :reviewed_by, "
            "reviewed_at = :reviewed_at, approved_at = :approved_at "
            "WHERE id = :application_id AND status = 'pending'"
        ),
        {
            "application_id": application_id,
            "status": status,
            "reviewed_by": reviewed_by,
            "reviewed_at": reviewed_at,
            "approved_at": approved_at,
        },
    )
    if result.rowcount != 1:
        raise RuntimeError("locked loan application changed during review")


def insert_repayment_schedule(
    connection: Connection,
    *,
    application_id: int,
    monthly_installment: int,
    due_dates: list[date],
) -> None:
    connection.execute(
        text(
            "INSERT INTO loan_repayments "
            "(loan_application_id, installment_number, due_date, amount, status) "
            "VALUES (:application_id, :installment_number, :due_date, :amount, 'scheduled')"
        ),
        [
            {
                "application_id": application_id,
                "installment_number": installment_number,
                "due_date": due_date,
                "amount": monthly_installment,
            }
            for installment_number, due_date in enumerate(due_dates, start=1)
        ],
    )


def list_customer_applications(
    connection: Connection,
    *,
    user_id: int,
) -> list[dict[str, object]]:
    rows = connection.execute(
        text(
            "SELECT id, user_id, product_id, product_code, product_name, principal_amount, "
            "term_months, monthly_installment, status, created_at, reviewed_at, reviewed_by, "
            "approved_at FROM loan_applications WHERE user_id = :user_id "
            "ORDER BY created_at DESC, id DESC"
        ),
        {"user_id": user_id},
    ).mappings()
    return [dict(row) for row in rows]


def list_pending_applications(
    connection: Connection,
    *,
    limit: int,
    offset: int,
) -> list[dict[str, object]]:
    rows = connection.execute(
        text(
            "SELECT a.id, a.user_id, u.name AS customer_name, a.product_code, a.product_name, "
            "a.principal_amount, a.term_months, a.monthly_installment, a.created_at "
            "FROM loan_applications AS a JOIN users AS u ON u.id = a.user_id "
            "WHERE a.status = 'pending' ORDER BY a.created_at, a.id "
            "LIMIT :limit OFFSET :offset"
        ),
        {"limit": limit, "offset": offset},
    ).mappings()
    return [dict(row) for row in rows]


def list_repayments(
    connection: Connection,
    *,
    application_id: int,
) -> list[dict[str, object]]:
    rows = connection.execute(
        text(
            "SELECT id, installment_number, due_date, amount, status, processed_at, paid_at "
            "FROM loan_repayments WHERE loan_application_id = :application_id "
            "ORDER BY installment_number"
        ),
        {"application_id": application_id},
    ).mappings()
    return [dict(row) for row in rows]


def list_repayments_for_applications(
    connection: Connection,
    *,
    application_ids: list[int],
) -> dict[int, list[dict[str, object]]]:
    if not application_ids:
        return {}
    placeholders = ", ".join(f":application_id_{index}" for index in range(len(application_ids)))
    parameters = {
        f"application_id_{index}": application_id
        for index, application_id in enumerate(application_ids)
    }
    rows = connection.execute(
        text(
            "SELECT id, loan_application_id, installment_number, due_date, amount, status, "
            "processed_at, paid_at FROM loan_repayments "
            f"WHERE loan_application_id IN ({placeholders}) "
            "ORDER BY loan_application_id, installment_number"
        ),
        parameters,
    ).mappings()
    result: dict[int, list[dict[str, object]]] = {}
    for row in rows:
        application_id = int(row["loan_application_id"])
        result.setdefault(application_id, []).append(dict(row))
    return result


def due_repayment_candidates(connection: Connection, as_of_date: date) -> list[tuple[int, int]]:
    rows = connection.execute(
        text(
            "SELECT id, loan_application_id FROM loan_repayments "
            "WHERE status = 'scheduled' AND due_date <= :as_of_date "
            "ORDER BY due_date, loan_application_id, installment_number"
        ),
        {"as_of_date": as_of_date},
    ).all()
    return [(int(row[0]), int(row[1])) for row in rows]


def lock_repayment(
    connection: Connection,
    *,
    repayment_id: int,
    application_id: int,
) -> dict[str, object] | None:
    row = (
        connection.execute(
            text(
                "SELECT id, loan_application_id, installment_number, due_date, amount, status "
                "FROM loan_repayments WHERE id = :repayment_id "
                "AND loan_application_id = :application_id FOR UPDATE WAIT 3"
            ),
            {"repayment_id": repayment_id, "application_id": application_id},
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


def lock_overdue_repayments(
    connection: Connection,
    *,
    application_id: int,
) -> list[dict[str, object]]:
    rows = connection.execute(
        text(
            "SELECT id, loan_application_id, installment_number, due_date, amount, status "
            "FROM loan_repayments WHERE loan_application_id = :application_id "
            "AND status = 'overdue' ORDER BY installment_number FOR UPDATE WAIT 3"
        ),
        {"application_id": application_id},
    ).mappings()
    return [dict(row) for row in rows]


def update_repayment_status(
    connection: Connection,
    *,
    repayment_id: int,
    expected_status: str,
    new_status: str,
    processed_at: datetime,
    paid_at: datetime | None,
) -> None:
    result = connection.execute(
        text(
            "UPDATE loan_repayments SET status = :new_status, processed_at = :processed_at, "
            "paid_at = :paid_at WHERE id = :repayment_id AND status = :expected_status"
        ),
        {
            "repayment_id": repayment_id,
            "expected_status": expected_status,
            "new_status": new_status,
            "processed_at": processed_at,
            "paid_at": paid_at,
        },
    )
    if result.rowcount != 1:
        raise RuntimeError("locked repayment changed during processing")


def has_open_repayments(connection: Connection, application_id: int) -> bool:
    return (
        connection.execute(
            text(
                "SELECT 1 FROM loan_repayments WHERE loan_application_id = :application_id "
                "AND status IN ('scheduled', 'overdue') LIMIT 1"
            ),
            {"application_id": application_id},
        ).first()
        is not None
    )


def mark_application_repaid(connection: Connection, application_id: int) -> None:
    result = connection.execute(
        text(
            "UPDATE loan_applications SET status = 'repaid' "
            "WHERE id = :application_id AND status = 'repaying'"
        ),
        {"application_id": application_id},
    )
    if result.rowcount != 1:
        raise RuntimeError("locked loan application changed during repayment")
