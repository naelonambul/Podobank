from dataclasses import dataclass
from typing import Protocol

import httpx

KAKAO_USER_INFO_URL = "https://kapi.kakao.com/v2/user/me"


@dataclass(frozen=True)
class KakaoIdentity:
    subject: str
    display_name: str | None = None


class KakaoProviderError(RuntimeError):
    """A transport or response error from Kakao's user information API."""


class InvalidKakaoToken(KakaoProviderError):
    """Kakao rejected the submitted access token."""


class KakaoProvider(Protocol):
    def verify_access_token(self, access_token: str) -> KakaoIdentity: ...


class HttpKakaoProvider:
    def __init__(self, *, timeout_seconds: float = 5.0) -> None:
        self.timeout_seconds = timeout_seconds

    def verify_access_token(self, access_token: str) -> KakaoIdentity:
        try:
            response = httpx.get(
                KAKAO_USER_INFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as error:
            if error.response.status_code in {401, 403}:
                raise InvalidKakaoToken("Kakao access token was rejected") from error
            raise KakaoProviderError("Kakao user verification is unavailable") from error
        except (httpx.RequestError, ValueError) as error:
            raise KakaoProviderError("Kakao user verification is unavailable") from error

        subject = payload.get("id") if isinstance(payload, dict) else None
        if subject is None:
            raise KakaoProviderError("Kakao returned an invalid user response")
        name = None
        if isinstance(payload, dict):
            account = payload.get("kakao_account")
            profile = account.get("profile") if isinstance(account, dict) else None
            properties = payload.get("properties")
            if isinstance(account, dict) and isinstance(account.get("name"), str):
                name = account["name"]
            elif isinstance(profile, dict) and isinstance(profile.get("nickname"), str):
                name = profile["nickname"]
            elif isinstance(properties, dict) and isinstance(properties.get("nickname"), str):
                name = properties["nickname"]
        return KakaoIdentity(subject=str(subject), display_name=name)
