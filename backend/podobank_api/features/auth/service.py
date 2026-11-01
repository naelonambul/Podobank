from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from podobank_api.features.accounts.service import create_default_account
from podobank_api.features.auth import sql
from podobank_api.features.auth.kakao import KakaoIdentity
from podobank_api.settings import Settings

_password_hash = PasswordHash.recommended()


@dataclass(frozen=True)
class AuthenticatedUser:
    id: int
    name: str
    phone_number: str
    role: str
    auth_method: str
    age: int | None = None
    gender: str | None = None
    marital_status: str | None = None
    is_employed: bool | None = None


class AuthError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hash.verify(password, password_hash)
    except (TypeError, ValueError):
        return False


def _to_user(row: dict[str, Any], auth_method: str) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=int(row["id"]),
        name=str(row["name"]),
        phone_number=str(row["phone_number"]),
        role=str(row["role"]),
        auth_method=auth_method,
        age=int(row["age"]) if row["age"] is not None else None,
        gender=str(row["gender"]) if row["gender"] is not None else None,
        marital_status=(str(row["marital_status"]) if row["marital_status"] is not None else None),
        is_employed=bool(row["is_employed"]) if row["is_employed"] is not None else None,
    )


def _make_session_token(user_id: int, settings: Settings, auth_method: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "auth_method": auth_method,
        "iat": now,
        "exp": now + timedelta(seconds=settings.session_ttl_seconds),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _result(
    engine: Engine,
    settings: Settings,
    row: dict[str, Any],
    is_new_user: bool,
    auth_method: str,
) -> dict[str, Any]:
    from podobank_api.features.accounts.service import get_account_for_user

    user = _to_user(row, auth_method)
    account = get_account_for_user(engine, user.id) if user.role == "customer" else None
    if user.role == "customer" and account is None:
        raise RuntimeError("authenticated customer has no account")
    return {
        "user": user,
        "account": account,
        "is_new_user": is_new_user,
        "session_token": _make_session_token(user.id, settings, auth_method),
    }


def login_with_kakao(
    engine: Engine,
    settings: Settings,
    identity: KakaoIdentity,
    *,
    phone_number: str | None,
    name: str | None,
    age: int | None,
    gender: str | None,
    marital_status: str | None,
    is_employed: bool | None,
    password: str | None,
) -> dict[str, Any]:
    hashed_password = hash_password(password) if password else None
    try:
        with engine.begin() as connection:
            row = sql.user_by_kakao_subject(connection, identity.subject)
            is_new_user = row is None
            if row is None:
                if (
                    phone_number is None
                    or age is None
                    or gender is None
                    or marital_status is None
                    or is_employed is None
                ):
                    raise AuthError(422, "profile details are required for first login")
                if sql.user_by_phone(connection, phone_number):
                    raise AuthError(409, "phone number is already registered")
                user_id = sql.insert_customer(
                    connection,
                    name=name or identity.display_name or "카카오 고객",
                    phone_number=phone_number,
                    kakao_subject=identity.subject,
                    password_hash=hashed_password,
                    age=age,
                    gender=gender,
                    marital_status=marital_status,
                    is_employed=is_employed,
                )
                create_default_account(connection, user_id)
                row = sql.user_by_id(connection, user_id)
            elif row["role"] != "customer":
                raise AuthError(403, "Kakao login is available to customers only")
            else:
                create_default_account(connection, int(row["id"]))
            if row is None:
                raise RuntimeError("user was not created")
    except AuthError:
        raise
    except IntegrityError as error:
        with engine.connect() as connection:
            existing = sql.user_by_kakao_subject(connection, identity.subject)
        if existing is None:
            raise AuthError(409, "phone number is already registered") from error
        row = existing
        is_new_user = False
        with engine.begin() as transaction:
            create_default_account(transaction, int(row["id"]))

    return _result(engine, settings, row, is_new_user, "kakao")


def login_with_password(
    engine: Engine,
    settings: Settings,
    phone_number: str,
    password: str,
) -> dict[str, Any]:
    with engine.connect() as connection:
        row = sql.user_by_phone(connection, phone_number)
    if (
        row is None
        or row["password_hash"] is None
        or not verify_password(password, str(row["password_hash"]))
    ):
        raise AuthError(401, "invalid phone number or password")
    return _result(engine, settings, row, is_new_user=False, auth_method="local")


def set_customer_password(
    engine: Engine,
    user_id: int,
    password: str,
    *,
    auth_method: str,
) -> None:
    if auth_method != "kakao":
        raise AuthError(403, "sign in with Kakao before setting a local password")
    password_hash = hash_password(password)
    with engine.begin() as connection:
        if not sql.set_password(connection, user_id, password_hash):
            raise AuthError(403, "only customers can set a local password")


def resolve_session(engine: Engine, settings: Settings, token: str) -> AuthenticatedUser:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "sub", "auth_method"]},
        )
        user_id = int(payload["sub"])
        auth_method = str(payload["auth_method"])
        if auth_method not in {"kakao", "local"}:
            raise ValueError("unknown authentication method")
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as error:
        raise AuthError(401, "authentication required") from error

    with engine.connect() as connection:
        row = sql.user_by_id(connection, user_id)
    if row is None:
        raise AuthError(401, "authentication required")
    return _to_user(row, auth_method)
