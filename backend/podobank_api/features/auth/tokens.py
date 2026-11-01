from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Response
from jwt.exceptions import PyJWTError

from podobank_api.settings import Settings

SESSION_COOKIE_NAME = "podobank_session"
KAKAO_SIGNUP_COOKIE_NAME = "podobank_kakao_signup"
KAKAO_STATE_COOKIE_NAME = "podobank_kakao_state"
JWT_ALGORITHM = "HS256"
KAKAO_SIGNUP_TTL_SECONDS = 300
KAKAO_STATE_TTL_SECONDS = 300


def issue_session_token(user_id: int, settings: Settings) -> str:
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.jwt_lifetime_minutes)
    return jwt.encode(
        {"sub": str(user_id), "purpose": "session", "iat": now, "exp": expires_at},
        settings.jwt_secret,
        algorithm=JWT_ALGORITHM,
    )


def decode_session_token(token: str, settings: Settings) -> int:
    claims = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[JWT_ALGORITHM],
        options={"require": ["sub", "purpose", "iat", "exp"]},
    )
    subject = claims.get("sub")
    if (
        claims.get("purpose") != "session"
        or not isinstance(subject, str)
        or not subject.isdecimal()
    ):
        raise PyJWTError("invalid session subject")
    user_id = int(subject)
    if user_id < 1:
        raise PyJWTError("invalid session subject")
    return user_id


def issue_kakao_signup_token(subject: str, name: str, settings: Settings) -> str:
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=KAKAO_SIGNUP_TTL_SECONDS)
    return jwt.encode(
        {"sub": subject, "name": name, "purpose": "kakao_signup", "iat": now, "exp": expires_at},
        settings.jwt_secret,
        algorithm=JWT_ALGORITHM,
    )


def decode_kakao_signup_token(token: str, settings: Settings) -> tuple[str, str]:
    claims = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[JWT_ALGORITHM],
        options={"require": ["sub", "name", "purpose", "iat", "exp"]},
    )
    subject = claims.get("sub")
    name = claims.get("name")
    if (
        claims.get("purpose") != "kakao_signup"
        or not isinstance(subject, str)
        or not subject
        or not isinstance(name, str)
        or not name
    ):
        raise PyJWTError("invalid signup token")
    return subject, name


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.jwt_lifetime_minutes * 60,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def set_kakao_signup_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=KAKAO_SIGNUP_COOKIE_NAME,
        value=token,
        max_age=KAKAO_SIGNUP_TTL_SECONDS,
        path="/auth/kakao",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def set_kakao_state_cookie(response: Response, state: str, settings: Settings) -> None:
    response.set_cookie(
        key=KAKAO_STATE_COOKIE_NAME,
        value=state,
        max_age=KAKAO_STATE_TTL_SECONDS,
        path="/auth/kakao",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def clear_kakao_state_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=KAKAO_STATE_COOKIE_NAME,
        path="/auth/kakao",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        key=KAKAO_SIGNUP_COOKIE_NAME,
        path="/auth/kakao",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    clear_kakao_state_cookie(response, settings)
