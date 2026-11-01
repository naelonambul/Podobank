import json
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from podobank_api.settings import PLACEHOLDER_KAKAO_KEY, PLACEHOLDER_KAKAO_SECRET

TOKEN_URL = "https://kauth.kakao.com/oauth/token"
USER_INFO_URL = "https://kapi.kakao.com/v2/user/me"
AUTHORIZATION_URL = "https://kauth.kakao.com/oauth/authorize"


class KakaoError(RuntimeError):
    """Base class for safe, user-facing Kakao authentication failures."""


class KakaoAuthorizationError(KakaoError):
    """The supplied authorization code or access token was rejected."""


class KakaoProviderUnavailable(KakaoError):
    """Kakao could not be reached or returned an invalid response."""


class KakaoConfigurationError(KakaoError):
    """Kakao credentials are not configured for this environment."""


@dataclass(frozen=True)
class KakaoProfile:
    subject: str
    name: str


class KakaoProvider:
    def __init__(
        self,
        *,
        rest_api_key: str,
        client_secret: str,
        redirect_uri: str,
        transport_factory: Callable[[], httpx.BaseTransport] | None = None,
    ) -> None:
        self._rest_api_key = rest_api_key
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._transport_factory = transport_factory

    def _validate_configuration(self) -> None:
        if (
            not self._rest_api_key
            or self._rest_api_key == PLACEHOLDER_KAKAO_KEY
            or not self._client_secret
            or self._client_secret == PLACEHOLDER_KAKAO_SECRET
        ):
            raise KakaoConfigurationError("Kakao login is not configured")

    def get_authorization_url(self, state: str) -> str:
        self._validate_configuration()
        parameters = {
            "response_type": "code",
            "client_id": self._rest_api_key,
            "redirect_uri": self._redirect_uri,
            "state": state,
        }
        return f"{AUTHORIZATION_URL}?{urlencode(parameters)}"

    def get_profile(self, authorization_code: str) -> KakaoProfile:
        self._validate_configuration()
        try:
            transport = self._transport_factory() if self._transport_factory is not None else None
            with httpx.Client(timeout=5.0, transport=transport) as client:
                token_response = client.post(
                    TOKEN_URL,
                    data={
                        "grant_type": "authorization_code",
                        "client_id": self._rest_api_key,
                        "client_secret": self._client_secret,
                        "redirect_uri": self._redirect_uri,
                        "code": authorization_code,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
                )
                if token_response.status_code in {400, 401}:
                    raise KakaoAuthorizationError("Kakao authorization code was rejected")
                token_response.raise_for_status()
                token_data = token_response.json()
                if not isinstance(token_data, dict):
                    raise KakaoProviderUnavailable("Kakao returned an invalid token response")
                access_token = token_data.get("access_token")
                if not isinstance(access_token, str) or not access_token:
                    raise KakaoProviderUnavailable("Kakao returned an invalid token response")

                profile_response = client.get(
                    USER_INFO_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={
                        "property_keys": json.dumps(
                            ["kakao_account.profile.nickname"], separators=(",", ":")
                        )
                    },
                )
                if profile_response.status_code in {400, 401}:
                    raise KakaoAuthorizationError("Kakao access token was rejected")
                profile_response.raise_for_status()
                profile_data = profile_response.json()
        except KakaoError:
            raise
        except httpx.HTTPStatusError as error:
            raise KakaoProviderUnavailable("Kakao returned an unsuccessful response") from error
        except (httpx.RequestError, ValueError) as error:
            raise KakaoProviderUnavailable("Kakao could not be reached") from error

        if not isinstance(profile_data, dict):
            raise KakaoProviderUnavailable("Kakao returned an invalid profile response")

        subject = profile_data.get("id")
        account = profile_data.get("kakao_account")
        profile = account.get("profile") if isinstance(account, dict) else None
        name = profile.get("nickname") if isinstance(profile, dict) else None
        if not name:
            properties = profile_data.get("properties")
            name = properties.get("nickname") if isinstance(properties, dict) else None
        if (
            not isinstance(subject, (int, str))
            or isinstance(subject, bool)
            or not str(subject).strip()
            or not isinstance(name, str)
            or not name.strip()
        ):
            raise KakaoProviderUnavailable("Kakao profile is missing its subject or nickname")
        return KakaoProfile(subject=str(subject), name=name.strip())
