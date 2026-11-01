import os
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_DATABASE_URL = "sqlite:///./data/podobank.db"
SUPPORTED_ENVIRONMENTS = {"development", "test", "production"}


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: str

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if environ is None else environ
        app_env = values.get("APP_ENV", "development").strip().lower()
        database_url = values.get("DATABASE_URL", DEFAULT_DATABASE_URL).strip()

        if app_env not in SUPPORTED_ENVIRONMENTS:
            raise ValueError("APP_ENV must be one of: " + ", ".join(sorted(SUPPORTED_ENVIRONMENTS)))
        if not database_url:
            raise ValueError("DATABASE_URL must not be empty")

        return cls(app_env=app_env, database_url=database_url)
