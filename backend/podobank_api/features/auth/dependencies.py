from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request

from podobank_api.features.auth.service import AuthenticatedUser, AuthError, resolve_session

SESSION_COOKIE_NAME = "podobank_session"


def get_current_user(
    request: Request,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> AuthenticatedUser:
    if not session_token:
        raise HTTPException(status_code=401, detail="authentication required")
    try:
        return resolve_session(request.app.state.engine, request.app.state.settings, session_token)
    except AuthError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error


def get_current_customer(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    if user.role != "customer":
        raise HTTPException(status_code=403, detail="customer access required")
    return user


def get_current_staff(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    if user.role != "bank_employee":
        raise HTTPException(status_code=403, detail="bank employee access required")
    return user
