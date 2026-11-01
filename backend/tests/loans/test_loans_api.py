from datetime import UTC, date, datetime
from unittest.mock import patch

from podobank_api.features.loans.service import first_due_date, process_due_repayments
from tests.support import ApiTestCase


class LoansApiTests(ApiTestCase):
    def test_seeded_products_and_active_application_limit(self) -> None:
        products = self.client.get("/loan-products").json()
        self.assertEqual(len(products), 3)
        self.assertEqual(
            [
                (row["principal_krw"], row["term_months"], row["monthly_installment_krw"])
                for row in products
            ],
            [(30_000_000, 60, 500_000), (96_000_000, 24, 4_000_000), (360_000_000, 360, 1_000_000)],
        )
        _user, token = self.register_customer(
            access_token="loan-application",
            phone_number="01055550014",
        )
        first = self.client.post("/loans/applications", json={"product_id": products[0]["id"]})
        second = self.client.post("/loans/applications", json={"product_id": products[1]["id"]})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.set_session(token)
        self.assertEqual(self.client.get("/loans").json()[0]["status"], "pending")

    def test_employee_approves_application_and_schedule_starts_on_monthly_first(self) -> None:
        customer, customer_token = self.register_customer(
            access_token="loan-approval",
            phone_number="01055550015",
        )
        product = self.client.get("/loan-products").json()[0]
        application = self.client.post("/loans/applications", json={"product_id": product["id"]})
        loan_id = application.json()["loan_id"]

        self.set_session(customer_token)
        self.assertEqual(self.client.get("/staff/loans/applications").status_code, 403)
        staff_token = self.login_staff()
        pending = self.client.get("/staff/loans/applications", params={"query": "01055550015"})
        self.assertEqual(pending.status_code, 200)
        self.assertEqual(pending.json()[0]["id"], loan_id)

        fixed_approval = datetime(2025, 4, 1, 12, tzinfo=UTC)
        with patch("podobank_api.features.loans.service._now", return_value=fixed_approval):
            decision = self.client.post(
                f"/staff/loans/applications/{loan_id}/decision",
                json={"decision": "approve"},
            )
        self.assertEqual(decision.status_code, 200)
        self.assertEqual(decision.json()["status"], "repaying")
        self.assertEqual(
            self.client.post(
                f"/staff/loans/applications/{loan_id}/decision",
                json={"decision": "reject"},
            ).status_code,
            404,
        )

        self.set_session(customer_token)
        self.assertEqual(self.client.get("/accounts/me").json()["balance_krw"], 30_000_000)
        loan = self.client.get("/loans").json()[0]
        self.assertEqual(loan["installments"][0]["due_date"], "2025-05-01")
        self.assertEqual(loan["installments"][-1]["due_date"], "2030-04-01")
        self.set_session(staff_token)

    def test_worker_marks_arrears_and_manual_repayment_pays_oldest_multiples(self) -> None:
        customer, customer_token = self.register_customer(
            access_token="loan-arrears",
            phone_number="01055550016",
        )
        product = self.client.get("/loan-products").json()[0]
        loan_id = self.client.post(
            "/loans/applications",
            json={"product_id": product["id"]},
        ).json()["loan_id"]
        self.login_staff()
        fixed_approval = datetime(2025, 4, 1, 12, tzinfo=UTC)
        with patch("podobank_api.features.loans.service._now", return_value=fixed_approval):
            self.client.post(
                f"/staff/loans/applications/{loan_id}/decision", json={"decision": "approve"}
            )

        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE accounts SET balance_krw = 0 WHERE owner_user_id = ?",
                (customer["user"]["id"],),
            )
        first_run = process_due_repayments(self.engine, as_of=date(2025, 6, 1))
        second_run = process_due_repayments(self.engine, as_of=date(2025, 6, 1))
        self.assertEqual(first_run, {"paid": 0, "overdue": 2})
        self.assertEqual(second_run, {"paid": 0, "overdue": 0})

        self.set_session(customer_token)
        self.client.post("/accounts/me/deposits", json={"amount_krw": 1_000_000})
        invalid = self.client.post(
            f"/loans/{loan_id}/repayments",
            json={"amount_krw": 750_000},
        )
        self.assertEqual(invalid.status_code, 422)
        repayment = self.client.post(
            f"/loans/{loan_id}/repayments",
            json={"amount_krw": 1_000_000},
        )
        self.assertEqual(repayment.status_code, 200)
        self.assertEqual(repayment.json()["balance_krw"], 0)
        schedule = self.client.get("/loans").json()[0]["installments"]
        self.assertEqual([item["status"] for item in schedule[:2]], ["paid", "paid"])

    def test_worker_debits_a_due_installment_once(self) -> None:
        _customer, customer_token = self.register_customer(
            access_token="loan-auto-payment",
            phone_number="01055550017",
        )
        product = self.client.get("/loan-products").json()[0]
        loan_id = self.client.post(
            "/loans/applications", json={"product_id": product["id"]}
        ).json()["loan_id"]
        self.login_staff()
        fixed_approval = datetime(2025, 4, 1, 12, tzinfo=UTC)
        with patch("podobank_api.features.loans.service._now", return_value=fixed_approval):
            self.client.post(
                f"/staff/loans/applications/{loan_id}/decision", json={"decision": "approve"}
            )

        self.assertEqual(
            process_due_repayments(self.engine, as_of=date(2025, 5, 1)),
            {"paid": 1, "overdue": 0},
        )
        self.assertEqual(
            process_due_repayments(self.engine, as_of=date(2025, 5, 1)),
            {"paid": 0, "overdue": 0},
        )
        self.set_session(customer_token)
        self.assertEqual(self.client.get("/accounts/me").json()["balance_krw"], 29_500_000)
        self.assertEqual(self.client.get("/loans").json()[0]["installments"][0]["status"], "paid")

    def test_rejected_application_allows_a_new_application(self) -> None:
        products = self.client.get("/loan-products").json()
        _customer, customer_token = self.register_customer(
            access_token="loan-reject",
            phone_number="01055550018",
        )
        first = self.client.post("/loans/applications", json={"product_id": products[0]["id"]})
        self.login_staff()
        result = self.client.post(
            f"/staff/loans/applications/{first.json()['loan_id']}/decision",
            json={"decision": "reject"},
        )
        self.assertEqual(result.status_code, 200)
        self.set_session(customer_token)
        self.assertEqual(
            self.client.post(
                "/loans/applications", json={"product_id": products[1]["id"]}
            ).status_code,
            201,
        )

    def test_first_due_date_waits_one_month_then_uses_month_start(self) -> None:
        self.assertEqual(first_due_date(datetime(2025, 4, 1, tzinfo=UTC)), date(2025, 5, 1))
        self.assertEqual(first_due_date(datetime(2025, 4, 30, tzinfo=UTC)), date(2025, 6, 1))
