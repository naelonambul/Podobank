import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from podobank_api.app import create_app
from podobank_api.database import create_database_engine
from podobank_api.settings import Settings


class HealthEndpointTests(unittest.TestCase):
    def test_health_endpoint_reports_ok(self) -> None:
        with tempfile.TemporaryDirectory(prefix="podobank-health-") as directory:
            settings = Settings(
                app_env="test",
                database_url=f"sqlite:///{Path(directory) / 'health.db'}",
                jwt_secret="test-secret-that-is-long-enough-for-hmac-signing",
                session_ttl_seconds=3600,
                staff_initial_phone="01099990000",
                staff_initial_password="staff-test-password",
                cors_allowed_origins=("http://localhost:5173",),
                cookie_secure=False,
            )
            engine = create_database_engine(settings.database_url)
            with TestClient(create_app(settings, engine=engine)) as client:
                response = client.get("/health")
            engine.dispose()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
