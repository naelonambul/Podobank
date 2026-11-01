from dataclasses import dataclass


@dataclass(frozen=True)
class AuthenticatedUser:
    id: int
    name: str
    phone_number: str
    role: str


@dataclass(frozen=True)
class KakaoSignupData:
    phone_number: str
    age: int
    gender: str
    marital_status: str
    is_employed: bool
    password: str | None
