import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.engine import Engine

from podobank_api.database import get_engine
from podobank_api.features.auth.dependencies import (
    SESSION_COOKIE_NAME,
    get_current_customer,
    get_current_user,
)
from podobank_api.features.auth.kakao import (
    InvalidKakaoToken,
    KakaoProviderError,
)
from podobank_api.features.auth.service import (
    AuthenticatedUser,
    AuthError,
    login_with_kakao,
    login_with_password,
    set_customer_password,
)
from podobank_api.settings import Settings

router = APIRouter(prefix="/auth", tags=["authentication"])


class KakaoLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str = Field(min_length=1, max_length=4096)
    phone_number: str | None = Field(default=None, min_length=10, max_length=14)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    age: int | None = Field(default=None, ge=1, le=120)
    gender: Literal["male", "female"] | None = None
    marital_status: Literal["single", "married"] | None = None
    is_employed: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("password", mode="before")
    @classmethod
    def blank_password_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("phone_number")
    @classmethod
    def normalize_phone_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = re.sub(r"\D", "", value)
        if len(normalized) not in {10, 11} or not normalized.startswith("01"):
            raise ValueError("phone number must be a valid Korean mobile number")
        return normalized


class LocalLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone_number: str = Field(min_length=10, max_length=14)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("phone_number")
    @classmethod
    def normalize_phone_number(cls, value: str) -> str:
        normalized = re.sub(r"\D", "", value)
        if len(normalized) not in {10, 11} or not normalized.startswith("01"):
            raise ValueError("phone number must be a valid Korean mobile number")
        return normalized


class PasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone_number: str
    role: str
    age: int | None = None
    gender: str | None = None
    marital_status: str | None = None
    is_employed: bool | None = None


class AccountSummary(BaseModel):
    account_number: str
    balance_krw: int


class AuthResponse(BaseModel):
    is_new_user: bool
    user: UserResponse
    account: AccountSummary | None = None


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.session_ttl_seconds,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _auth_response(
    result: dict[str, object], response: Response, settings: Settings
) -> AuthResponse:
    _set_session_cookie(response, str(result["session_token"]), settings)
    account = result["account"]
    return AuthResponse(
        is_new_user=bool(result["is_new_user"]),
        user=UserResponse.model_validate(result["user"]),
        account=(
            AccountSummary(
                account_number=str(account["account_number"]),
                balance_krw=int(account["balance_krw"]),
            )
            if isinstance(account, dict)
            else None
        ),
    )


def _raise_auth_error(error: AuthError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.detail) from error


@router.post("/kakao", response_model=AuthResponse)
def kakao_login(
    body: KakaoLoginRequest,
    request: Request,
    response: Response,
    engine: Annotated[Engine, Depends(get_engine)],
) -> AuthResponse:
    try:
        identity = request.app.state.kakao_provider.verify_access_token(body.access_token)
    except InvalidKakaoToken as error:
        raise HTTPException(status_code=401, detail="Kakao access token is invalid") from error
    except KakaoProviderError as error:
        raise HTTPException(
            status_code=503, detail="Kakao login is temporarily unavailable"
        ) from error

    try:
        result = login_with_kakao(
            engine,
            request.app.state.settings,
            identity,
            phone_number=body.phone_number,
            name=body.name,
            age=body.age,
            gender=body.gender,
            marital_status=body.marital_status,
            is_employed=body.is_employed,
            password=body.password,
        )
    except AuthError as error:
        _raise_auth_error(error)
    return _auth_response(result, response, request.app.state.settings)


@router.post("/local", response_model=AuthResponse)
def local_login(
    body: LocalLoginRequest,
    request: Request,
    response: Response,
    engine: Annotated[Engine, Depends(get_engine)],
) -> AuthResponse:
    try:
        result = login_with_password(
            engine,
            request.app.state.settings,
            body.phone_number,
            body.password,
        )
    except AuthError as error:
        _raise_auth_error(error)
    return _auth_response(result, response, request.app.state.settings)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def set_password(
    body: PasswordRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_customer)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> Response:
    try:
        set_customer_password(engine, user.id, body.password, auth_method=user.auth_method)
    except AuthError as error:
        _raise_auth_error(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, request: Request) -> Response:
    settings: Settings = request.app.state.settings
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserResponse)
def who_am_i(user: Annotated[AuthenticatedUser, Depends(get_current_user)]) -> UserResponse:
    return UserResponse.model_validate(user)
