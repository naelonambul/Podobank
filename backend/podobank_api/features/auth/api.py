import secrets
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from jwt.exceptions import PyJWTError

from podobank_api.features.auth.dependencies import (
    get_auth_service,
    get_current_user,
    require_customer,
)
from podobank_api.features.auth.kakao import (
    KakaoAuthorizationError,
    KakaoConfigurationError,
    KakaoProviderUnavailable,
)
from podobank_api.features.auth.models import AuthenticatedUser, KakaoSignupData
from podobank_api.features.auth.schemas import (
    KakaoCodeRequest,
    KakaoSignupRequest,
    LocalLoginRequest,
    PasswordSetupRequest,
)
from podobank_api.features.auth.service import (
    AuthService,
    CustomerOnlyError,
    DuplicatePhoneError,
    InvalidCredentialsError,
    KakaoRegistrationRequiredError,
    PasswordAlreadySetError,
)
from podobank_api.features.auth.tokens import (
    KAKAO_SIGNUP_COOKIE_NAME,
    KAKAO_STATE_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    clear_auth_cookies,
    clear_kakao_state_cookie,
    decode_kakao_signup_token,
    issue_kakao_signup_token,
    issue_session_token,
    set_kakao_signup_cookie,
    set_kakao_state_cookie,
    set_session_cookie,
)
from podobank_api.settings import Settings

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session(response: Response, user: AuthenticatedUser, settings: Settings) -> None:
    set_session_cookie(response, issue_session_token(user.id, settings), settings)


def _clear_signup_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=KAKAO_SIGNUP_COOKIE_NAME,
        path="/auth/kakao",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )


@router.post("/kakao/state")
def begin_kakao_login(
    http_request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict[str, str]:
    state = secrets.token_urlsafe(32)
    try:
        authorization_url = service.get_kakao_authorization_url(state)
    except KakaoConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "kakao_not_configured", "message": "Kakao login is not configured"},
        ) from error

    set_kakao_state_cookie(response, state, http_request.app.state.settings)
    response.headers["Cache-Control"] = "no-store"
    return {"authorization_url": authorization_url}


def _raise_kakao_error(error: KakaoAuthorizationError | KakaoProviderUnavailable) -> None:
    if isinstance(error, KakaoAuthorizationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "kakao_authorization_failed", "message": "Kakao login failed"},
        ) from error
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": "kakao_unavailable", "message": "Kakao login is temporarily unavailable"},
    ) from error


@router.post("/kakao/login")
def kakao_login(
    request: KakaoCodeRequest,
    http_request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    state_cookie: Annotated[str | None, Cookie(alias=KAKAO_STATE_COOKIE_NAME)] = None,
) -> dict[str, str]:
    if state_cookie is None or not secrets.compare_digest(state_cookie, request.state):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "kakao_state_invalid", "message": "Kakao login request is invalid"},
        )

    try:
        user = service.login_with_kakao(request.code)
    except KakaoRegistrationRequiredError as error:
        settings = http_request.app.state.settings
        clear_kakao_state_cookie(response, settings)
        token = issue_kakao_signup_token(
            error.profile.subject,
            error.profile.name,
            settings,
        )
        response.delete_cookie(
            key=SESSION_COOKIE_NAME,
            path="/",
            secure=settings.auth_cookie_secure,
            httponly=True,
            samesite="lax",
        )
        set_kakao_signup_cookie(response, token, settings)
        return {"status": "registration_required"}
    except (KakaoAuthorizationError, KakaoProviderUnavailable) as error:
        _raise_kakao_error(error)
    except KakaoConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "kakao_not_configured", "message": "Kakao login is not configured"},
        ) from error
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        ) from error

    settings = http_request.app.state.settings
    clear_kakao_state_cookie(response, settings)
    _set_session(response, user, settings)
    _clear_signup_cookie(response, settings)
    return {"status": "authenticated"}


@router.post("/kakao/signup")
def kakao_signup(
    request: KakaoSignupRequest,
    http_request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    signup_token: Annotated[str | None, Cookie(alias=KAKAO_SIGNUP_COOKIE_NAME)] = None,
) -> dict[str, str]:
    settings = http_request.app.state.settings
    if signup_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "signup_session_required", "message": "Kakao signup session expired"},
        )
    try:
        subject, name = decode_kakao_signup_token(signup_token, settings)
    except PyJWTError as error:
        response.delete_cookie(
            key=KAKAO_SIGNUP_COOKIE_NAME,
            path="/auth/kakao",
            secure=settings.auth_cookie_secure,
            httponly=True,
            samesite="lax",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "signup_session_expired", "message": "Kakao signup session expired"},
        ) from error

    try:
        user = service.complete_kakao_signup(
            subject=subject,
            name=name,
            signup=KakaoSignupData(
                phone_number=request.phone_number,
                age=request.age,
                gender=request.gender,
                marital_status=request.marital_status,
                is_employed=request.is_employed,
                password=request.password,
            ),
        )
    except DuplicatePhoneError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "phone_already_registered",
                "message": "phone number is already registered",
            },
        ) from error
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid signup session",
        ) from error

    _set_session(response, user, settings)
    _clear_signup_cookie(response, settings)
    return {"status": "authenticated"}


@router.post("/login")
def local_login(
    request: LocalLoginRequest,
    http_request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict[str, str]:
    try:
        user = service.login_locally(
            phone_number=request.phone_number,
            password=request.password,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid phone number or password",
        ) from error

    settings = http_request.app.state.settings
    _set_session(response, user, settings)
    _clear_signup_cookie(response, settings)
    return {"status": "authenticated"}


@router.post("/password")
def set_customer_password(
    request: PasswordSetupRequest,
    user: Annotated[AuthenticatedUser, Depends(require_customer)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict[str, str]:
    try:
        service.set_customer_password(user_id=user.id, password=request.password)
    except PasswordAlreadySetError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "password_already_set", "message": "password has already been set"},
        ) from error
    except CustomerOnlyError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="customer access required",
        ) from error
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        ) from error
    return {"status": "password_set"}


@router.post("/logout")
def logout(http_request: Request, response: Response) -> dict[str, str]:
    clear_auth_cookies(response, http_request.app.state.settings)
    return {"status": "logged_out"}


@router.get("/me")
def get_current_user_profile(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> dict[str, int | str]:
    return {
        "id": user.id,
        "name": user.name,
        "phone_number": user.phone_number,
        "role": user.role,
    }
