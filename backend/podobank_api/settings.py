import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

SUPPORTED_ENVIRONMENTS = {"development", "test", "production"}
DEFAULT_JWT_SECRET = "development-only-change-this-secret-32-chars"
PLACEHOLDER_KAKAO_KEY = "replace-with-kakao-rest-api-key"
PLACEHOLDER_KAKAO_SECRET = "replace-with-kakao-client-secret"


def _parse_bool(value: str, *, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def _parse_origins(value: str, *, name: str = "FRONTEND_ORIGINS") -> tuple[str, ...]:
    origins = tuple(origin.strip().rstrip("/") for origin in value.split(",") if origin.strip())
    if not origins:
        raise ValueError(f"{name} must contain at least one origin")

    for origin in origins:
        parsed = urlsplit(origin)
        if (
            origin == "*"
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(f"{name} must contain explicit HTTP or HTTPS origins")

    if len(origins) != len(set(origins)):
        raise ValueError(f"{name} must not contain duplicates")
    return origins


def _parse_origin(value: str, *, name: str) -> str:
    origins = _parse_origins(value, name=name)
    if len(origins) != 1:
        raise ValueError(f"{name} must contain exactly one origin")
    return origins[0]


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: str
    api_origin: str
    kakao_rest_api_key: str
    kakao_client_secret: str
    kakao_redirect_uri: str
    jwt_secret: str
    jwt_lifetime_minutes: int
    auth_cookie_secure: bool
    frontend_origins: tuple[str, ...]
    bank_employee_phone: str
    bank_employee_password: str

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if environ is None else environ
        app_env = values.get("APP_ENV", "development").strip().lower()
        database_url = values.get("DATABASE_URL", "").strip()

        if app_env not in SUPPORTED_ENVIRONMENTS:
            raise ValueError("APP_ENV must be one of: " + ", ".join(sorted(SUPPORTED_ENVIRONMENTS)))
        if not database_url:
            raise ValueError("DATABASE_URL must be set to the MariaDB connection URL")

        try:
            jwt_lifetime_minutes = int(values.get("JWT_LIFETIME_MINUTES", "120"))
        except ValueError as error:
            raise ValueError("JWT_LIFETIME_MINUTES must be a positive integer") from error
        if jwt_lifetime_minutes < 1:
            raise ValueError("JWT_LIFETIME_MINUTES must be a positive integer")

        cookie_secure_default = "true" if app_env == "production" else "false"
        return cls(
            app_env=app_env,
            database_url=database_url,
            api_origin=_parse_origin(
                values.get("API_ORIGIN", "http://localhost:8000"),
                name="API_ORIGIN",
            ),
            kakao_rest_api_key=values.get("KAKAO_REST_API_KEY", PLACEHOLDER_KAKAO_KEY).strip(),
            kakao_client_secret=values.get("KAKAO_CLIENT_SECRET", PLACEHOLDER_KAKAO_SECRET).strip(),
            kakao_redirect_uri=values.get(
                "KAKAO_REDIRECT_URI", "http://localhost:5173/auth/kakao/callback"
            ).strip(),
            jwt_secret=values.get("JWT_SECRET", DEFAULT_JWT_SECRET).strip(),
            jwt_lifetime_minutes=jwt_lifetime_minutes,
            auth_cookie_secure=_parse_bool(
                values.get("AUTH_COOKIE_SECURE", cookie_secure_default),
                name="AUTH_COOKIE_SECURE",
            ),
            frontend_origins=_parse_origins(
                values.get(
                    "FRONTEND_ORIGINS",
                    "http://localhost:5173,http://localhost:8080",
                )
            ),
            bank_employee_phone=values.get("BANK_EMPLOYEE_PHONE", "01000000002").strip(),
            bank_employee_password=values.get(
                "BANK_EMPLOYEE_PASSWORD", "local-demo-employee-password"
            ),
        )

    def validate_application_security(self) -> None:
        if self.app_env != "production":
            return

        if len(self.jwt_secret) < 32 or self.jwt_secret == DEFAULT_JWT_SECRET:
            raise ValueError(
                "production requires a non-placeholder JWT_SECRET of at least 32 characters"
            )
        if not self.auth_cookie_secure:
            raise ValueError("AUTH_COOKIE_SECURE must be true in production")
        if not self.kakao_rest_api_key or self.kakao_rest_api_key == PLACEHOLDER_KAKAO_KEY:
            raise ValueError("production requires a configured KAKAO_REST_API_KEY")
        if not self.kakao_client_secret or self.kakao_client_secret == PLACEHOLDER_KAKAO_SECRET:
            raise ValueError("production requires a configured KAKAO_CLIENT_SECRET")

        redirect_uri = urlsplit(self.kakao_redirect_uri)
        if redirect_uri.scheme != "https" or not redirect_uri.netloc:
            raise ValueError("production KAKAO_REDIRECT_URI must use HTTPS")
        if any(urlsplit(origin).scheme != "https" for origin in self.frontend_origins):
            raise ValueError("production FRONTEND_ORIGINS must use HTTPS")
        api_origin = urlsplit(self.api_origin)
        if api_origin.scheme != "https":
            raise ValueError("production API_ORIGIN must use HTTPS")
        api_hostname = api_origin.hostname
        if any(urlsplit(origin).hostname != api_hostname for origin in self.frontend_origins):
            raise ValueError(
                "production API_ORIGIN and FRONTEND_ORIGINS must use the same hostname "
                "with SameSite=Lax cookies"
            )
        if redirect_uri.hostname != api_hostname:
            raise ValueError(
                "production API_ORIGIN and KAKAO_REDIRECT_URI must use the same hostname "
                "with SameSite=Lax cookies"
            )

    def validate_employee_seed(self) -> None:
        if not self.bank_employee_phone:
            raise ValueError("BANK_EMPLOYEE_PHONE must be set before initializing sample data")
        if len(self.bank_employee_password) < 8:
            raise ValueError("BANK_EMPLOYEE_PASSWORD must contain at least 8 characters")
