from collections.abc import Callable

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import Engine

from podobank_api.database import create_database_engine
from podobank_api.features.accounts.api import router as accounts_router
from podobank_api.features.accounts.service import AccountService
from podobank_api.features.auth.api import router as auth_router
from podobank_api.features.auth.kakao import KakaoProvider
from podobank_api.features.auth.service import AuthService
from podobank_api.settings import Settings


def create_app(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    kakao_transport_factory: Callable[[], httpx.BaseTransport] | None = None,
) -> FastAPI:
    app_settings = settings or Settings.from_environment()
    app_settings.validate_application_security()
    database_engine = engine or create_database_engine(app_settings.database_url)

    application = FastAPI(title="PodoBank API", version="0.1.0")
    application.state.settings = app_settings
    application.state.engine = database_engine
    application.state.auth_service = AuthService(
        database_engine,
        KakaoProvider(
            rest_api_key=app_settings.kakao_rest_api_key,
            client_secret=app_settings.kakao_client_secret,
            redirect_uri=app_settings.kakao_redirect_uri,
            transport_factory=kakao_transport_factory,
        ),
    )
    application.state.account_service = AccountService(database_engine)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.frontend_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Accept", "Content-Type"],
    )
    application.include_router(auth_router)
    application.include_router(accounts_router)

    @application.get("/health", tags=["system"])
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
