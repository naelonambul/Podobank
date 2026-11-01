from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.low_level import Type

_PASSWORD_HASHER = PasswordHasher(type=Type.ID)
_DUMMY_PASSWORD_HASH = _PASSWORD_HASHER.hash("not-a-real-podobank-password")


def hash_password(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    if not password_hash:
        try:
            _PASSWORD_HASHER.verify(_DUMMY_PASSWORD_HASH, password)
        except InvalidHashError, VerificationError:
            pass
        return False
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except InvalidHashError, VerificationError:
        return False
