from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import Engine

from podobank_api.database import create_database_engine, initialize_database
from podobank_api.features.accounts.api import router as accounts_router
from podobank_api.features.auth.api import router as auth_router
from podobank_api.features.auth.kakao import HttpKakaoProvider, KakaoProvider
from podobank_api.features.loans.api import router as loans_router
from podobank_api.features.transactions.api import router as transactions_router
from podobank_api.settings import Settings


def create_app(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    kakao_provider: KakaoProvider | None = None,
) -> FastAPI:
    app_settings = settings or Settings.from_environment()
    owns_engine = engine is None
    app_engine = engine or create_database_engine(app_settings.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        initialize_database(
            app_engine,
            staff_initial_phone=app_settings.staff_initial_phone,
            staff_initial_password=app_settings.staff_initial_password,
        )
        try:
            yield
        finally:
            if owns_engine:
                app_engine.dispose()

    app = FastAPI(title="PodoBank API", version="0.1.0", lifespan=lifespan)
    app.state.engine = app_engine
    app.state.settings = app_settings
    app.state.kakao_provider = kakao_provider or HttpKakaoProvider()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.cors_allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    app.include_router(auth_router)
    app.include_router(accounts_router)
    app.include_router(transactions_router)
    app.include_router(loans_router)

    @app.get("/health", tags=["system"])
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
