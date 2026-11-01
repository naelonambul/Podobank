from collections.abc import Callable

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from podobank_api.database import create_database_engine
from podobank_api.features.accounts.api import router as accounts_router
from podobank_api.features.accounts.service import AccountService
from podobank_api.features.auth.api import router as auth_router
from podobank_api.features.auth.kakao import KakaoProvider
from podobank_api.features.auth.service import AuthService
from podobank_api.features.loans.api import router as loans_router
from podobank_api.features.loans.service import LoanService
from podobank_api.features.transactions.api import router as transactions_router
from podobank_api.features.transactions.service import TransactionService
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

    @application.exception_handler(DBAPIError)
    def database_error_handler(_request: Request, _error: DBAPIError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "detail": {
                    "code": "database_unavailable",
                    "message": "database request failed",
                }
            },
        )

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
    application.state.transaction_service = TransactionService(database_engine)
    application.state.loan_service = LoanService(database_engine)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.frontend_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Accept", "Content-Type"],
    )
    application.include_router(auth_router)
    application.include_router(accounts_router)
    application.include_router(transactions_router)
    application.include_router(loans_router)

    @application.get("/health", tags=["system"])
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
