from podobank_api.features.auth.dependencies import SESSION_COOKIE_NAME
from tests.support import ApiTestCase


class AuthenticationApiTests(ApiTestCase):
    def test_kakao_signup_creates_profile_and_one_default_account(self) -> None:
        response = self.client.post(
            "/auth/kakao",
            json={
                "access_token": "new-customer",
                "phone_number": "010-5555-0001",
                "name": "가상 포도",
                "age": 28,
                "gender": "female",
                "marital_status": "single",
                "is_employed": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["is_new_user"])
        self.assertEqual(payload["user"]["name"], "가상 포도")
        self.assertEqual(payload["user"]["phone_number"], "01055550001")
        self.assertEqual(payload["user"]["role"], "customer")
        self.assertEqual(payload["account"]["balance_krw"], 0)
        self.assertIn("httponly", response.headers["set-cookie"].lower())
        self.assertNotIn("access_token", response.text)

        account_response = self.client.get("/accounts/me")
        self.assertEqual(account_response.status_code, 200)
        self.assertEqual(account_response.json(), payload["account"])

    def test_existing_kakao_login_reuses_account(self) -> None:
        first, token = self.register_customer(
            access_token="same-kakao-user",
            phone_number="01055550002",
        )
        self.set_session(None)
        response = self.client.post("/auth/kakao", json={"access_token": "same-kakao-user"})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_new_user"])
        self.assertEqual(response.json()["account"], first["account"])
        with self.engine.connect() as connection:
            account_count = connection.exec_driver_sql(
                "SELECT COUNT(*) FROM accounts WHERE owner_user_id = ?",
                (first["user"]["id"],),
            ).scalar_one()
        self.assertEqual(account_count, 1)
        self.assertNotEqual(token, "")

    def test_duplicate_phone_number_rejects_new_kakao_user(self) -> None:
        self.register_customer(access_token="first", phone_number="01055550003")
        self.set_session(None)
        response = self.client.post(
            "/auth/kakao",
            json={
                "access_token": "second",
                "phone_number": "01055550003",
                "age": 30,
                "gender": "male",
                "marital_status": "married",
                "is_employed": False,
            },
        )

        self.assertEqual(response.status_code, 409)

    def test_customer_without_password_cannot_use_local_login(self) -> None:
        self.register_customer(
            access_token="no-password",
            phone_number="01055550004",
            password="",
        )
        self.set_session(None)
        response = self.client.post(
            "/auth/local",
            json={"phone_number": "01055550004", "password": "a-valid-password"},
        )

        self.assertEqual(response.status_code, 401)

    def test_customer_can_set_password_after_kakao_login(self) -> None:
        user, _token = self.register_customer(
            access_token="password-customer",
            phone_number="01055550005",
        )
        set_response = self.client.post("/auth/password", json={"password": "customer-pass-1"})
        self.assertEqual(set_response.status_code, 204)
        with self.engine.connect() as connection:
            password_hash = connection.exec_driver_sql(
                "SELECT password_hash FROM users WHERE id = ?",
                (user["user"]["id"],),
            ).scalar_one()
        self.assertNotEqual(password_hash, "customer-pass-1")

        self.client.post("/auth/logout")
        self.assertIsNone(self.client.cookies.get(SESSION_COOKIE_NAME))
        response = self.client.post(
            "/auth/local",
            json={"phone_number": "01055550005", "password": "customer-pass-1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["id"], user["user"]["id"])
        self.assertIn("httponly", response.headers["set-cookie"].lower())

    def test_local_login_session_cannot_set_or_change_customer_password(self) -> None:
        self.register_customer(
            access_token="password-session",
            phone_number="01055550019",
            password="initial-pass-1",
        )
        self.set_session(None)
        login = self.client.post(
            "/auth/local",
            json={"phone_number": "01055550019", "password": "initial-pass-1"},
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(
            self.client.post("/auth/password", json={"password": "replacement-pass-2"}).status_code,
            403,
        )

    def test_staff_uses_local_login_and_customer_role_is_loaded_from_database(self) -> None:
        staff_token = self.login_staff()
        self.assertEqual(self.client.get("/auth/me").json()["role"], "bank_employee")
        self.assertEqual(self.client.get("/accounts/me").status_code, 403)

        customer, customer_token = self.register_customer(
            access_token="role-test",
            phone_number="01055550006",
        )
        self.set_session(customer_token)
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE users SET role = 'bank_employee' WHERE id = ?",
                (customer["user"]["id"],),
            )
        self.assertEqual(self.client.get("/accounts/me").status_code, 403)
        self.set_session(staff_token)

    def test_cors_allows_only_the_configured_frontend_origin(self) -> None:
        allowed = self.client.options(
            "/auth/kakao",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        self.assertEqual(
            allowed.headers.get("access-control-allow-origin"), "http://localhost:5173"
        )
        self.assertEqual(allowed.headers.get("access-control-allow-credentials"), "true")

        denied = self.client.options(
            "/auth/kakao",
            headers={
                "Origin": "http://untrusted.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertNotIn("access-control-allow-origin", denied.headers)

    def test_invalid_kakao_token_is_rejected(self) -> None:
        response = self.client.post("/auth/kakao", json={"access_token": "invalid-token"})
        self.assertEqual(response.status_code, 401)
