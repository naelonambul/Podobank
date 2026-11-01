from sqlalchemy.engine import Connection


def list_products(connection: Connection) -> list[dict[str, object]]:
    rows = connection.exec_driver_sql(
        "SELECT id, product_code, name, principal_krw, term_months, monthly_installment_krw "
        "FROM loan_products WHERE is_active = 1 ORDER BY id"
    ).all()
    return [dict(row._mapping) for row in rows]


def product_by_id(connection: Connection, product_id: int) -> dict[str, object] | None:
    row = connection.exec_driver_sql(
        "SELECT id, product_code, name, principal_krw, term_months, monthly_installment_krw "
        "FROM loan_products WHERE id = ? AND is_active = 1",
        (product_id,),
    ).first()
    return dict(row._mapping) if row else None


def active_loan_for_user(connection: Connection, user_id: int) -> dict[str, object] | None:
    row = connection.exec_driver_sql(
        "SELECT id, status FROM loans WHERE user_id = ? "
        "AND status IN ('pending', 'repaying') LIMIT 1",
        (user_id,),
    ).first()
    return dict(row._mapping) if row else None


def insert_loan_application(connection: Connection, user_id: int, product_id: int) -> int:
    result = connection.exec_driver_sql(
        "INSERT INTO loans (user_id, product_id, status) VALUES (?, ?, 'pending')",
        (user_id, product_id),
    )
    return int(result.lastrowid)


def loan_for_user(connection: Connection, loan_id: int, user_id: int) -> dict[str, object] | None:
    row = connection.exec_driver_sql(
        "SELECT l.id, l.user_id, l.product_id, l.status, l.applied_at, l.decided_at, "
        "l.approved_at, p.product_code, p.name AS product_name, p.principal_krw, "
        "p.term_months, p.monthly_installment_krw FROM loans AS l "
        "JOIN loan_products AS p ON p.id = l.product_id "
        "WHERE l.id = ? AND l.user_id = ?",
        (loan_id, user_id),
    ).first()
    return dict(row._mapping) if row else None


def list_user_loans(connection: Connection, user_id: int) -> list[dict[str, object]]:
    rows = connection.exec_driver_sql(
        "SELECT l.id, l.user_id, l.product_id, l.status, l.applied_at, l.decided_at, "
        "l.approved_at, p.product_code, p.name AS product_name, p.principal_krw, "
        "p.term_months, p.monthly_installment_krw FROM loans AS l "
        "JOIN loan_products AS p ON p.id = l.product_id "
        "WHERE l.user_id = ? ORDER BY l.id DESC",
        (user_id,),
    ).all()
    return [dict(row._mapping) for row in rows]


def list_installments(connection: Connection, loan_id: int) -> list[dict[str, object]]:
    rows = connection.exec_driver_sql(
        "SELECT installment_number, due_date, amount_krw, status, paid_at "
        "FROM loan_installments WHERE loan_id = ? ORDER BY installment_number",
        (loan_id,),
    ).all()
    return [dict(row._mapping) for row in rows]


def pending_application_for_staff(
    connection: Connection,
    loan_id: int,
) -> dict[str, object] | None:
    row = connection.exec_driver_sql(
        "SELECT l.id, l.user_id, l.product_id, l.status, l.applied_at, u.name, "
        "u.phone_number, a.account_number, p.name AS product_name, p.principal_krw, "
        "p.term_months, p.monthly_installment_krw FROM loans AS l "
        "JOIN users AS u ON u.id = l.user_id "
        "JOIN accounts AS a ON a.owner_user_id = u.id "
        "JOIN loan_products AS p ON p.id = l.product_id "
        "WHERE l.id = ? AND l.status = 'pending'",
        (loan_id,),
    ).first()
    return dict(row._mapping) if row else None


def list_pending_applications(
    connection: Connection,
    *,
    query: str | None,
    limit: int,
) -> list[dict[str, object]]:
    if query:
        pattern = f"%{query}%"
        rows = connection.exec_driver_sql(
            "SELECT l.id, l.user_id, l.status, l.applied_at, u.name, u.phone_number, "
            "a.account_number, p.name AS product_name, p.principal_krw, p.term_months, "
            "p.monthly_installment_krw FROM loans AS l "
            "JOIN users AS u ON u.id = l.user_id "
            "JOIN accounts AS a ON a.owner_user_id = u.id "
            "JOIN loan_products AS p ON p.id = l.product_id "
            "WHERE l.status = 'pending' AND (u.name LIKE ? OR u.phone_number LIKE ? "
            "OR a.account_number LIKE ?) ORDER BY l.applied_at, l.id LIMIT ?",
            (pattern, pattern, pattern, limit),
        ).all()
    else:
        rows = connection.exec_driver_sql(
            "SELECT l.id, l.user_id, l.status, l.applied_at, u.name, u.phone_number, "
            "a.account_number, p.name AS product_name, p.principal_krw, p.term_months, "
            "p.monthly_installment_krw FROM loans AS l "
            "JOIN users AS u ON u.id = l.user_id "
            "JOIN accounts AS a ON a.owner_user_id = u.id "
            "JOIN loan_products AS p ON p.id = l.product_id "
            "WHERE l.status = 'pending' ORDER BY l.applied_at, l.id LIMIT ?",
            (limit,),
        ).all()
    return [dict(row._mapping) for row in rows]


def set_decision(
    connection: Connection,
    loan_id: int,
    *,
    decision: str,
    decided_at: str,
    approved_at: str | None,
) -> bool:
    result = connection.exec_driver_sql(
        "UPDATE loans SET status = ?, decided_at = ?, approved_at = ? "
        "WHERE id = ? AND status = 'pending'",
        (decision, decided_at, approved_at, loan_id),
    )
    return result.rowcount == 1


def insert_installments(
    connection: Connection,
    loan_id: int,
    rows: list[tuple[int, str, int]],
) -> None:
    connection.exec_driver_sql(
        "INSERT INTO loan_installments (loan_id, installment_number, due_date, amount_krw, status) "
        "VALUES (?, ?, ?, ?, 'scheduled')",
        [(loan_id, number, due_date, amount) for number, due_date, amount in rows],
    )


def due_installment_ids(connection: Connection, due_date: str) -> list[int]:
    rows = connection.exec_driver_sql(
        "SELECT id FROM loan_installments WHERE status = 'scheduled' AND due_date <= ? "
        "ORDER BY due_date, loan_id, installment_number",
        (due_date,),
    ).all()
    return [int(row[0]) for row in rows]


def claim_due_installment(
    connection: Connection,
    installment_id: int,
    due_date: str,
) -> dict[str, object] | None:
    claimed = connection.exec_driver_sql(
        "UPDATE loan_installments SET status = 'processing' "
        "WHERE id = ? AND status = 'scheduled' AND due_date <= ?",
        (installment_id, due_date),
    )
    if claimed.rowcount != 1:
        return None
    row = connection.exec_driver_sql(
        "SELECT i.id, i.loan_id, i.installment_number, i.due_date, i.amount_krw, "
        "l.user_id FROM loan_installments AS i "
        "JOIN loans AS l ON l.id = i.loan_id WHERE i.id = ?",
        (installment_id,),
    ).first()
    return dict(row._mapping) if row else None


def finish_installment(
    connection: Connection,
    installment_id: int,
    *,
    status: str,
    paid_at: str | None,
) -> None:
    connection.exec_driver_sql(
        "UPDATE loan_installments SET status = ?, paid_at = ? "
        "WHERE id = ? AND status = 'processing'",
        (status, paid_at, installment_id),
    )


def overdue_installments(connection: Connection, loan_id: int) -> list[dict[str, object]]:
    rows = connection.exec_driver_sql(
        "SELECT id, installment_number, due_date, amount_krw FROM loan_installments "
        "WHERE loan_id = ? AND status = 'overdue' ORDER BY due_date, installment_number",
        (loan_id,),
    ).all()
    return [dict(row._mapping) for row in rows]


def claim_overdue_installments(connection: Connection, installment_ids: list[int]) -> bool:
    placeholders = ", ".join("?" for _ in installment_ids)
    result = connection.exec_driver_sql(
        f"UPDATE loan_installments SET status = 'processing' "
        f"WHERE status = 'overdue' AND id IN ({placeholders})",
        tuple(installment_ids),
    )
    return result.rowcount == len(installment_ids)


def has_unpaid_installments(connection: Connection, loan_id: int) -> bool:
    return bool(
        connection.exec_driver_sql(
            "SELECT 1 FROM loan_installments WHERE loan_id = ? AND status != 'paid' LIMIT 1",
            (loan_id,),
        ).first()
    )


def mark_loan_paid_off(connection: Connection, loan_id: int) -> None:
    connection.exec_driver_sql(
        "UPDATE loans SET status = 'paid_off' WHERE id = ? AND status = 'repaying'",
        (loan_id,),
    )
