import os
import unittest
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import text

from podobank_api.app import create_app
from podobank_api.database import create_database_engine, reset_database, validate_reset_target
from podobank_api.features.auth.kakao import TOKEN_URL, USER_INFO_URL
from podobank_api.features.auth.passwords import verify_password
from podobank_api.seed import DEMO_CUSTOMER_PHONE
from podobank_api.settings import Settings

TEST_EMPLOYEE_PHONE = "01000000009"
TEST_EMPLOYEE_PASSWORD = "test-employee-password"


class AuthenticationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_url = os.environ.get("DATABASE_URL", "")
        if not self.database_url:
            self.fail("DATABASE_URL must point to the isolated podobank_test database")
        validate_reset_target("test", self.database_url)
        self.engine = create_database_engine(self.database_url)
        reset_database(
            self.engine,
            app_env="test",
            employee_phone=TEST_EMPLOYEE_PHONE,
            employee_password=TEST_EMPLOYEE_PASSWORD,
        )
        self.settings = Settings.from_environment(
            {
                "APP_ENV": "test",
                "DATABASE_URL": self.database_url,
                "KAKAO_REST_API_KEY": "test-rest-api-key",
                "KAKAO_CLIENT_SECRET": "test-client-secret",
                "KAKAO_REDIRECT_URI": "http://localhost:5173/auth/kakao/callback",
                "JWT_SECRET": "test-only-secret-with-more-than-32-characters",
                "JWT_LIFETIME_MINUTES": "120",
                "AUTH_COOKIE_SECURE": "false",
                "FRONTEND_ORIGINS": "http://localhost:5173,http://localhost:8080",
                "BANK_EMPLOYEE_PHONE": TEST_EMPLOYEE_PHONE,
                "BANK_EMPLOYEE_PASSWORD": TEST_EMPLOYEE_PASSWORD,
            }
        )
        self.app = create_app(
            self.settings,
            engine=self.engine,
            kakao_transport_factory=lambda: httpx.MockTransport(self._kakao_response),
        )

    def tearDown(self) -> None:
        self.engine.dispose()

    @staticmethod
    def _kakao_response(request: httpx.Request) -> httpx.Response:
        if request.url.path == httpx.URL(TOKEN_URL).path:
            body = parse_qs(request.content.decode())
            code = body.get("code", [""])[0]
            if code == "provider-down":
                return httpx.Response(503, json={"error": "temporarily_unavailable"})
            if code == "invalid-code":
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": f"test-token-{code}"})

        if request.url.path == httpx.URL(USER_INFO_URL).path:
            code = request.headers["Authorization"].removeprefix("Bearer test-token-")
            subject_by_code = {
                "new-user": 101,
                "existing-user": 101,
                "different-user": 202,
                "password-user": 303,
                "provider-down": 404,
                "invalid-code": 505,
            }
            subject = subject_by_code[code]
            return httpx.Response(
                200,
                json={
                    "id": subject,
                    "kakao_account": {"profile": {"nickname": f"고객 {subject}"}},
                },
            )

        return httpx.Response(404, json={"error": "not_found"})

    def _complete_signup(
        self,
        client: TestClient,
        *,
        code: str,
        phone_number: str,
        password: str | None = None,
    ) -> httpx.Response:
        login_response = self._begin_kakao_login(client, code)
        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(login_response.json(), {"status": "registration_required"})
        self.assertIsNotNone(client.cookies.get("podobank_kakao_signup"))

        payload: dict[str, object] = {
            "phone_number": phone_number,
            "age": 30,
            "gender": "female",
            "marital_status": "single",
            "is_employed": True,
        }
        if password is not None:
            payload["password"] = password
        return client.post("/auth/kakao/signup", json=payload)

    def _begin_kakao_login(self, client: TestClient, code: str) -> httpx.Response:
        start = client.post("/auth/kakao/state")
        self.assertEqual(start.status_code, 200)
        authorization_url = urlsplit(start.json()["authorization_url"])
        state = parse_qs(authorization_url.query)["state"][0]
        self.assertEqual(authorization_url.scheme, "https")
        self.assertEqual(authorization_url.netloc, "kauth.kakao.com")
        return client.post("/auth/kakao/login", json={"code": code, "state": state})

    def test_kakao_signup_creates_one_account_and_subsequent_login_reuses_it(self) -> None:
        with TestClient(self.app) as client:
            signup = self._complete_signup(
                client,
                code="new-user",
                phone_number="01011110001",
                password="customer-password",
            )
            self.assertEqual(signup.status_code, 200)
            self.assertEqual(signup.json(), {"status": "authenticated"})
            self.assertIsNone(signup.json().get("token"))
            self.assertIsNotNone(client.cookies.get("podobank_session"))
            self.assertIsNone(client.cookies.get("podobank_kakao_signup"))

            cookie_headers = signup.headers.get_list("set-cookie")
            session_cookie = next(value for value in cookie_headers if "podobank_session=" in value)
            self.assertIn("httponly", session_cookie.lower())
            self.assertIn("samesite=lax", session_cookie.lower())
            self.assertNotIn("secure", session_cookie.lower())

            profile = client.get("/auth/me")
            account = client.get("/accounts/me")
            self.assertEqual(profile.status_code, 200)
            self.assertEqual(profile.json()["name"], "고객 101")
            self.assertEqual(profile.json()["role"], "customer")
            self.assertEqual(account.status_code, 200)
            self.assertEqual(account.json()["balance"], 0)

            login = self._begin_kakao_login(client, "existing-user")
            self.assertEqual(login.status_code, 200)
            self.assertEqual(login.json(), {"status": "authenticated"})
            self.assertIsNone(client.cookies.get("podobank_kakao_state"))

        with self.engine.connect() as connection:
            user_count = connection.execute(
                text("SELECT COUNT(*) FROM users WHERE kakao_subject = '101'")
            ).scalar_one()
            account_count = connection.execute(
                text(
                    "SELECT COUNT(*) FROM accounts "
                    "WHERE owner_user_id = (SELECT id FROM users WHERE kakao_subject = '101')"
                )
            ).scalar_one()
            password_hash = connection.execute(
                text("SELECT password_hash FROM users WHERE kakao_subject = '101'")
            ).scalar_one()

        self.assertEqual(user_count, 1)
        self.assertEqual(account_count, 1)
        self.assertTrue(password_hash.startswith("$argon2id$"))
        self.assertTrue(verify_password(password_hash, "customer-password"))

    def test_kakao_signup_token_cannot_authenticate_as_a_session(self) -> None:
        with TestClient(self.app) as client:
            login = self._begin_kakao_login(client, "new-user")
            self.assertEqual(login.status_code, 200)
            self.assertEqual(login.json(), {"status": "registration_required"})
            signup_token = client.cookies.get("podobank_kakao_signup")
            self.assertIsNotNone(signup_token)

            client.cookies.set("podobank_session", signup_token)
            protected_response = client.get("/auth/me")

        self.assertEqual(protected_response.status_code, 401)

    def test_duplicate_phone_does_not_link_another_kakao_subject(self) -> None:
        with TestClient(self.app) as client:
            response = self._complete_signup(
                client,
                code="different-user",
                phone_number=DEMO_CUSTOMER_PHONE,
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "phone_already_registered")
        with self.engine.connect() as connection:
            duplicate_subject_count = connection.execute(
                text("SELECT COUNT(*) FROM users WHERE kakao_subject = '202'")
            ).scalar_one()
        self.assertEqual(duplicate_subject_count, 0)

    def test_kakao_login_requires_the_browser_state_cookie(self) -> None:
        with TestClient(self.app) as client:
            missing_cookie = client.post(
                "/auth/kakao/login",
                json={"code": "new-user", "state": "client-supplied-state"},
            )
            self.assertEqual(missing_cookie.status_code, 401)
            self.assertEqual(missing_cookie.json()["detail"]["code"], "kakao_state_invalid")

            start = client.post("/auth/kakao/state")
            state = parse_qs(urlsplit(start.json()["authorization_url"]).query)["state"][0]
            wrong_state = client.post(
                "/auth/kakao/login",
                json={"code": "new-user", "state": f"{state}-wrong"},
            )
            self.assertEqual(wrong_state.status_code, 401)
            self.assertEqual(wrong_state.json()["detail"]["code"], "kakao_state_invalid")

            valid_state = client.post(
                "/auth/kakao/login",
                json={"code": "new-user", "state": state},
            )

        self.assertEqual(valid_state.status_code, 200)
        self.assertEqual(valid_state.json(), {"status": "registration_required"})
        state_cookie = next(
            value
            for value in start.headers.get_list("set-cookie")
            if "podobank_kakao_state=" in value
        )
        self.assertIn("httponly", state_cookie.lower())
        self.assertIn("samesite=lax", state_cookie.lower())

    def test_customer_can_set_a_password_once_after_kakao_signup(self) -> None:
        with TestClient(self.app) as client:
            signup = self._complete_signup(
                client,
                code="password-user",
                phone_number="01011110003",
            )
            self.assertEqual(signup.status_code, 200)

            missing_password = client.post(
                "/auth/login",
                json={"phone_number": "01011110003", "password": "any-password"},
            )
            unknown_phone = client.post(
                "/auth/login",
                json={"phone_number": "01099990003", "password": "any-password"},
            )
            self.assertEqual(missing_password.status_code, 401)
            self.assertEqual(unknown_phone.status_code, 401)
            self.assertEqual(unknown_phone.json(), missing_password.json())

            set_password = client.post("/auth/password", json={"password": "new-password"})
            self.assertEqual(set_password.status_code, 200)
            second_setup = client.post("/auth/password", json={"password": "other-password"})
            self.assertEqual(second_setup.status_code, 409)

            logout = client.post("/auth/logout")
            self.assertEqual(logout.status_code, 200)
            self.assertIsNone(client.cookies.get("podobank_session"))

            login = client.post(
                "/auth/login",
                json={"phone_number": "01011110003", "password": "new-password"},
            )
            self.assertEqual(login.status_code, 200)
            self.assertEqual(client.get("/auth/me").status_code, 200)

    def test_employee_uses_local_login_and_role_is_loaded_from_database(self) -> None:
        with TestClient(self.app) as client:
            login = client.post(
                "/auth/login",
                json={
                    "phone_number": TEST_EMPLOYEE_PHONE,
                    "password": TEST_EMPLOYEE_PASSWORD,
                },
            )
            self.assertEqual(login.status_code, 200)
            self.assertEqual(client.get("/auth/me").json()["role"], "bank_employee")
            self.assertEqual(client.get("/accounts/me").status_code, 404)

            with self.engine.begin() as connection:
                connection.execute(
                    text("UPDATE users SET role = 'customer' WHERE phone_number = :phone"),
                    {"phone": TEST_EMPLOYEE_PHONE},
                )
            self.assertEqual(client.get("/auth/me").json()["role"], "customer")

    def test_kakao_provider_failures_have_stable_responses(self) -> None:
        with TestClient(self.app) as client:
            invalid_code = self._begin_kakao_login(client, "invalid-code")
            unavailable = self._begin_kakao_login(client, "provider-down")

        self.assertEqual(invalid_code.status_code, 401)
        self.assertEqual(invalid_code.json()["detail"]["code"], "kakao_authorization_failed")
        self.assertEqual(unavailable.status_code, 503)
        self.assertEqual(unavailable.json()["detail"]["code"], "kakao_unavailable")

    def test_credentialed_cors_allows_only_configured_origins(self) -> None:
        with TestClient(self.app) as client:
            allowed = client.options(
                "/auth/login",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            denied = client.options(
                "/auth/login",
                headers={
                    "Origin": "https://attacker.example",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )

        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.headers["access-control-allow-origin"], "http://localhost:5173")
        self.assertEqual(allowed.headers["access-control-allow-credentials"], "true")
        self.assertEqual(denied.status_code, 400)
        self.assertNotIn("access-control-allow-origin", denied.headers)


if __name__ == "__main__":
    unittest.main()
