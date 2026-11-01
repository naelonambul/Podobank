import os
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_DATABASE_URL = "sqlite:///./data/podobank.db"
SUPPORTED_ENVIRONMENTS = {"development", "test", "production"}
DEFAULT_JWT_SECRET = "local-development-only-secret-change-before-production"


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: str
    jwt_secret: str
    session_ttl_seconds: int
    staff_initial_phone: str
    staff_initial_password: str
    cors_allowed_origins: tuple[str, ...]
    cookie_secure: bool

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if environ is None else environ
        app_env = values.get("APP_ENV", "development").strip().lower()
        database_url = values.get("DATABASE_URL", DEFAULT_DATABASE_URL).strip()
        jwt_secret = values.get("JWT_SECRET", DEFAULT_JWT_SECRET).strip()
        session_ttl_seconds = int(values.get("SESSION_TTL_SECONDS", "86400"))
        staff_initial_phone = values.get("STAFF_INITIAL_PHONE", "01099990000").strip()
        staff_initial_password = values.get("STAFF_INITIAL_PASSWORD", "")
        cors_allowed_origins = tuple(
            origin.strip().rstrip("/")
            for origin in values.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
            if origin.strip()
        )
        cookie_secure = values.get("COOKIE_SECURE", "true" if app_env == "production" else "false")
        cookie_secure = cookie_secure.strip().lower() in {"1", "true", "yes", "on"}

        if app_env not in SUPPORTED_ENVIRONMENTS:
            raise ValueError("APP_ENV must be one of: " + ", ".join(sorted(SUPPORTED_ENVIRONMENTS)))
        if not database_url:
            raise ValueError("DATABASE_URL must not be empty")
        if session_ttl_seconds <= 0:
            raise ValueError("SESSION_TTL_SECONDS must be positive")
        if not staff_initial_phone:
            raise ValueError("STAFF_INITIAL_PHONE must not be empty")
        if not jwt_secret:
            raise ValueError("JWT_SECRET must not be empty")
        if not cors_allowed_origins or "*" in cors_allowed_origins:
            raise ValueError("CORS_ALLOWED_ORIGINS must list explicit origins and cannot use '*'")
        if app_env == "production" and (len(jwt_secret) < 32 or jwt_secret == DEFAULT_JWT_SECRET):
            raise ValueError("JWT_SECRET must be at least 32 characters in production")
        if app_env == "production" and not cookie_secure:
            raise ValueError("COOKIE_SECURE must be enabled in production")

        return cls(
            app_env=app_env,
            database_url=database_url,
            jwt_secret=jwt_secret,
            session_ttl_seconds=session_ttl_seconds,
            staff_initial_phone=staff_initial_phone,
            staff_initial_password=staff_initial_password,
            cors_allowed_origins=cors_allowed_origins,
            cookie_secure=cookie_secure,
        )
