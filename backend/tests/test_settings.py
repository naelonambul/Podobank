import unittest

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


if __name__ == "__main__":
    unittest.main()
