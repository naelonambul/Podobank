from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from jwt.exceptions import PyJWTError

from podobank_api.features.auth.models import AuthenticatedUser
from podobank_api.features.auth.service import AuthService
from podobank_api.features.auth.tokens import SESSION_COOKIE_NAME, decode_session_token


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


def get_current_user(
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> AuthenticatedUser:
    if session_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    try:
        user_id = decode_session_token(session_token, request.app.state.settings)
    except PyJWTError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        ) from error

    user = service.get_user(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    return user


def require_customer(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    if user.role != "customer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="customer access required"
        )
    return user


def require_bank_employee(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    if user.role != "bank_employee":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="bank employee access required"
        )
    return user
