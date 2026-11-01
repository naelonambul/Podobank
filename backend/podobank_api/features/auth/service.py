from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from podobank_api.features.accounts.service import ensure_default_account
from podobank_api.features.auth import sql
from podobank_api.features.auth.kakao import KakaoProfile, KakaoProvider
from podobank_api.features.auth.models import AuthenticatedUser, KakaoSignupData
from podobank_api.features.auth.passwords import hash_password, verify_password


class AuthError(RuntimeError):
    """Base class for expected authentication and registration failures."""


class InvalidCredentialsError(AuthError):
    """Login credentials do not match an account with a local password."""


class KakaoRegistrationRequiredError(AuthError):
    def __init__(self, profile: KakaoProfile) -> None:
        super().__init__("Kakao profile is not registered")
        self.profile = profile


class DuplicatePhoneError(AuthError):
    """A phone number is already assigned to another account."""


class PasswordAlreadySetError(AuthError):
    """The customer has already completed one-time password setup."""


class CustomerOnlyError(AuthError):
    """The requested operation is available only to customers."""


class AuthService:
    def __init__(self, engine: Engine, kakao_provider: KakaoProvider) -> None:
        self._engine = engine
        self._kakao_provider = kakao_provider

    def get_kakao_authorization_url(self, state: str) -> str:
        return self._kakao_provider.get_authorization_url(state)

    def get_user(self, user_id: int) -> AuthenticatedUser | None:
        with self._engine.connect() as connection:
            row = sql.find_user_by_id(connection, user_id)
        return self._identity(row) if row is not None else None

    def login_with_kakao(self, authorization_code: str) -> AuthenticatedUser:
        profile = self._kakao_provider.get_profile(authorization_code)
        with self._engine.connect() as connection:
            row = sql.find_user_by_kakao_subject(connection, profile.subject)
        if row is None:
            raise KakaoRegistrationRequiredError(profile)
        if row["role"] != "customer":
            raise InvalidCredentialsError("invalid credentials")
        return self._identity(row)

    def complete_kakao_signup(
        self,
        *,
        subject: str,
        name: str,
        signup: KakaoSignupData,
    ) -> AuthenticatedUser:
        password_hash = hash_password(signup.password) if signup.password is not None else None
        try:
            with self._engine.begin() as connection:
                existing = sql.find_user_by_kakao_subject(connection, subject)
                if existing is not None:
                    if existing["role"] != "customer":
                        raise InvalidCredentialsError("invalid credentials")
                    ensure_default_account(connection, int(existing["id"]))
                    return self._identity(existing)

                phone_owner = sql.find_user_by_phone(connection, signup.phone_number)
                if phone_owner is not None:
                    raise DuplicatePhoneError("phone number is already registered")

                user_id = sql.insert_customer(
                    connection,
                    name=name,
                    phone_number=signup.phone_number,
                    kakao_subject=subject,
                    password_hash=password_hash,
                    age=signup.age,
                    gender=signup.gender,
                    marital_status=signup.marital_status,
                    is_employed=signup.is_employed,
                )
                ensure_default_account(connection, user_id)
                return AuthenticatedUser(
                    id=user_id,
                    name=name,
                    phone_number=signup.phone_number,
                    role="customer",
                )
        except IntegrityError as error:
            return self._resolve_signup_race(
                subject=subject,
                phone_number=signup.phone_number,
                conflict=error,
            )

    def login_locally(self, *, phone_number: str, password: str) -> AuthenticatedUser:
        with self._engine.connect() as connection:
            row = sql.find_user_by_phone(connection, phone_number)
        if row is None:
            verify_password(None, password)
            raise InvalidCredentialsError("invalid credentials")
        if not verify_password(row["password_hash"], password):
            raise InvalidCredentialsError("invalid credentials")
        return self._identity(row)

    def set_customer_password(self, *, user_id: int, password: str) -> None:
        password_hash = hash_password(password)
        with self._engine.begin() as connection:
            changed = sql.set_password_if_unset(
                connection,
                user_id=user_id,
                password_hash=password_hash,
            )
            if changed == 1:
                return

            current = sql.find_user_by_id(connection, user_id)
            if current is None:
                raise InvalidCredentialsError("invalid session")
            if current["role"] != "customer":
                raise CustomerOnlyError("only customers can set a local password")
            raise PasswordAlreadySetError("a local password has already been set")

    def _resolve_signup_race(
        self,
        *,
        subject: str,
        phone_number: str,
        conflict: IntegrityError,
    ) -> AuthenticatedUser:
        with self._engine.connect() as connection:
            existing = sql.find_user_by_kakao_subject(connection, subject)
            phone_owner = sql.find_user_by_phone(connection, phone_number)
        if existing is not None and existing["role"] == "customer":
            return self._identity(existing)
        if phone_owner is not None:
            raise DuplicatePhoneError("phone number is already registered")
        raise conflict

    @staticmethod
    def _identity(row: dict[str, object]) -> AuthenticatedUser:
        return AuthenticatedUser(
            id=int(row["id"]),
            name=str(row["name"]),
            phone_number=str(row["phone_number"]),
            role=str(row["role"]),
        )
