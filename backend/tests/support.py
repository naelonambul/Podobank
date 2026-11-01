import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from podobank_api.app import create_app
from podobank_api.database import create_database_engine
from podobank_api.features.auth.dependencies import SESSION_COOKIE_NAME
from podobank_api.features.auth.kakao import InvalidKakaoToken, KakaoIdentity
from podobank_api.settings import Settings


class FakeKakaoProvider:
    def verify_access_token(self, access_token: str) -> KakaoIdentity:
        if access_token == "invalid-token":
            raise InvalidKakaoToken("invalid token")
        return KakaoIdentity(
            subject=f"subject:{access_token}", display_name=f"사용자 {access_token}"
        )


class ApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(prefix="podobank-test-")
        database_path = Path(self.temporary_directory.name) / "test.db"
        self.settings = Settings(
            app_env="test",
            database_url=f"sqlite:///{database_path}",
            jwt_secret="test-secret-that-is-long-enough-for-hmac-signing",
            session_ttl_seconds=3600,
            staff_initial_phone="01099990000",
            staff_initial_password="staff-test-password",
            cors_allowed_origins=("http://localhost:5173",),
            cookie_secure=False,
        )
        self.engine = create_database_engine(self.settings.database_url)
        self.client = TestClient(
            create_app(
                self.settings,
                engine=self.engine,
                kakao_provider=FakeKakaoProvider(),
            )
        )
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        self.engine.dispose()
        self.temporary_directory.cleanup()

    def register_customer(
        self,
        *,
        access_token: str,
        phone_number: str,
        name: str = "테스트 사용자",
        password: str | None = None,
    ) -> tuple[dict[str, object], str]:
        body: dict[str, object] = {
            "access_token": access_token,
            "phone_number": phone_number,
            "name": name,
            "age": 30,
            "gender": "female",
            "marital_status": "single",
            "is_employed": True,
        }
        if password is not None:
            body["password"] = password
        response = self.client.post("/auth/kakao", json=body)
        if response.status_code != 200:
            raise AssertionError(f"registration failed: {response.status_code} {response.text}")
        token = self.client.cookies.get(SESSION_COOKIE_NAME)
        if not token:
            raise AssertionError("registration did not set the session cookie")
        return response.json(), token

    def set_session(self, token: str | None) -> None:
        self.client.cookies.clear()
        if token is not None:
            self.client.cookies.set(SESSION_COOKIE_NAME, token)

    def login_staff(self) -> str:
        self.client.cookies.clear()
        response = self.client.post(
            "/auth/local",
            json={
                "phone_number": self.settings.staff_initial_phone,
                "password": self.settings.staff_initial_password,
            },
        )
        if response.status_code != 200:
            raise AssertionError(f"staff login failed: {response.status_code} {response.text}")
        token = self.client.cookies.get(SESSION_COOKIE_NAME)
        if not token:
            raise AssertionError("staff login did not set the session cookie")
        return token
