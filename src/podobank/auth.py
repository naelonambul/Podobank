"""Sandbox partner authentication dependencies."""

from __future__ import annotations

import secrets
from collections.abc import Callable, Mapping
from typing import Annotated

from fastapi import Header, HTTPException, Request


def require_partner(keys: Mapping[str, str]) -> Callable[..., str]:
    def authenticate(authorization: str | None = Header(default=None)) -> str:
        if authorization is not None:
            scheme, separator, token = authorization.partition(" ")
            if separator and scheme.lower() == "bearer" and token:
                for partner_id, expected_key in keys.items():
                    if secrets.compare_digest(token, expected_key):
                        return partner_id
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthorized", "message": "A valid sandbox partner key is required."},
            headers={"WWW-Authenticate": "Bearer"},
        )

    return authenticate


def authenticate_request(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Authenticate a request against the app's configured sandbox partner keys."""
    return require_partner(request.app.state.settings.partner_keys)(authorization)
