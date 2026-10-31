"""FastAPI application factory for the Podobank synthetic banking API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from podobank.config import Settings
from podobank.db import Database
from podobank.routes import accounts_router, events_router, sandbox_router, transfers_router


def create_app(database_url: str, settings: Settings) -> FastAPI:
    database = Database(database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        database.initialize_schema()
        yield
        database.dispose()

    app = FastAPI(
        title="Podobank Sandbox API",
        summary="Synthetic banking activity for MLOps bootcamp data pipelines.",
        description=(
            "All accounts, events, and partner payments in this API are simulated. "
            "No real bank account or payment rail is connected. Use the interactive "
            "request explorer to create a sandbox and poll its event feed."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.database = database
    app.state.settings = settings
    app.include_router(sandbox_router)
    app.include_router(accounts_router)
    app.include_router(transfers_router)
    app.include_router(events_router)

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(_: Request, __: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "invalid_request",
                    "message": "The request parameters or body are invalid.",
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, error: StarletteHTTPException) -> JSONResponse:
        detail = error.detail
        if isinstance(detail, dict) and isinstance(detail.get("code"), str):
            code = detail["code"]
            message = str(detail.get("message", "The request could not be completed."))
            error_body = {"code": code, "message": message}
            error_body.update(
                {key: value for key, value in detail.items() if key not in {"code", "message"}}
            )
        else:
            code = {401: "unauthorized", 404: "not_found"}.get(error.status_code, "request_failed")
            message = str(detail)
            error_body = {"code": code, "message": message}
        return JSONResponse(
            status_code=error.status_code,
            content={"error": error_body},
            headers=error.headers,
        )

    return app
