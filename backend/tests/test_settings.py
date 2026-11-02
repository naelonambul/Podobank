import os
import unittest
from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import patch

from podobank_api.cli import main as cli_main
from podobank_api.settings import Settings


class ProductionSecuritySettingsTests(unittest.TestCase):
    def _settings(self, *, api_origin: str, frontend_origin: str) -> Settings:
        return Settings.from_environment(
            {
                "APP_ENV": "production",
                "DATABASE_URL": "mysql+pymysql://user:password@db:3306/podobank",
                "API_ORIGIN": api_origin,
                "KAKAO_REST_API_KEY": "configured-rest-api-key",
                "KAKAO_CLIENT_SECRET": "configured-client-secret",
                "KAKAO_REDIRECT_URI": f"{frontend_origin}/auth/kakao/callback",
                "JWT_SECRET": "production-only-secret-with-more-than-32-characters",
                "AUTH_COOKIE_SECURE": "true",
                "FRONTEND_ORIGINS": frontend_origin,
            }
        )

    def test_production_allows_same_hostname_for_frontend_api_and_callback(self) -> None:
        settings = self._settings(
            api_origin="https://podobank.example.com:8000",
            frontend_origin="https://podobank.example.com",
        )

        settings.validate_application_security()

    def test_production_rejects_cross_site_frontend_and_api_hosts(self) -> None:
        settings = self._settings(
            api_origin="https://api.example.com",
            frontend_origin="https://podobank.example.net",
        )

        with self.assertRaisesRegex(ValueError, "same hostname"):
            settings.validate_application_security()


class DemoCustomerSeedSettingsTests(unittest.TestCase):
    def _settings(self, demo_customer_password: str = "") -> Settings:
        return Settings.from_environment(
            {
                "APP_ENV": "development",
                "DATABASE_URL": "mysql+pymysql://user:password@localhost:3306/podobank_dev",
                "DEMO_CUSTOMER_PASSWORD": demo_customer_password,
            }
        )

    def test_seed_demo_data_requires_demo_password(self) -> None:
        settings = self._settings()
        validator = getattr(settings, "validate_demo_customer_seed", None)
        if not callable(validator):
            self.fail("Settings.validate_demo_customer_seed has not been implemented")

        with self.assertRaisesRegex(ValueError, "at least 8 characters"):
            validator()
        with self.assertRaisesRegex(ValueError, "at least 8 characters"):
            self._settings("short").validate_demo_customer_seed()

        self._settings("local-demo-customer-password").validate_demo_customer_seed()

        errors = StringIO()
        environment = {
            "APP_ENV": "development",
            "DATABASE_URL": "mysql+pymysql://user:password@127.0.0.1:3306/podobank_dev",
            "DEMO_CUSTOMER_PASSWORD": "short",
        }
        with (
            patch.dict(os.environ, environment),
            patch("podobank_api.cli.create_database_engine") as engine_factory,
            redirect_stderr(errors),
        ):
            exit_code = cli_main(["seed-demo-data"])

        self.assertEqual(exit_code, 2)
        self.assertNotIn("short", errors.getvalue())
        engine_factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
