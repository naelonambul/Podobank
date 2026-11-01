from pydantic import BaseModel, Field


class KakaoCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=2048)
    state: str = Field(min_length=1, max_length=256)


class KakaoSignupRequest(BaseModel):
    phone_number: str = Field(pattern=r"^[0-9]{10,15}$")
    age: int = Field(ge=1, le=120)
    gender: str = Field(pattern=r"^(male|female)$")
    marital_status: str = Field(pattern=r"^(single|married)$")
    is_employed: bool
    password: str | None = Field(default=None, min_length=8, max_length=128)


class LocalLoginRequest(BaseModel):
    phone_number: str = Field(pattern=r"^[0-9]{10,15}$")
    password: str = Field(min_length=1, max_length=128)


class PasswordSetupRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)
