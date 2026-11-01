from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from podobank_api.features.accounts.schemas import RecipientSearchRequest
from podobank_api.features.accounts.service import AccountService
from podobank_api.features.auth.dependencies import get_current_user, require_customer
from podobank_api.features.auth.models import AuthenticatedUser

router = APIRouter(prefix="/accounts", tags=["accounts"])


def get_account_service(request: Request) -> AccountService:
    return request.app.state.account_service


@router.get("/me")
def get_my_account(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[AccountService, Depends(get_account_service)],
) -> dict[str, int | str]:
    try:
        account = service.get_for_user(user.id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="account not found") from error
    return {
        "id": account.id,
        "account_number": account.account_number,
        "balance": account.balance,
    }


@router.get("/recipients")
def list_recipients(
    user: Annotated[AuthenticatedUser, Depends(require_customer)],
    service: Annotated[AccountService, Depends(get_account_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> dict[str, object]:
    return _recipient_page(service, user.id, None, limit, offset)


@router.post("/recipients/search")
def search_recipients(
    request: RecipientSearchRequest,
    user: Annotated[AuthenticatedUser, Depends(require_customer)],
    service: Annotated[AccountService, Depends(get_account_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> dict[str, object]:
    return _recipient_page(service, user.id, request.query, limit, offset)


def _recipient_page(
    service: AccountService,
    user_id: int,
    query: str | None,
    limit: int,
    offset: int,
) -> dict[str, object]:
    try:
        recipients = service.find_recipients(
            current_user_id=user_id,
            query=query,
            limit=limit,
            offset=offset,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail="invalid recipient query") from error
    return {
        "items": [
            {
                "account_id": recipient.account_id,
                "name": recipient.name,
                "masked_account_number": recipient.masked_account_number,
                "phone_suffix": recipient.phone_suffix,
            }
            for recipient in recipients
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/me/ledger")
def get_my_ledger(
    user: Annotated[AuthenticatedUser, Depends(require_customer)],
    service: Annotated[AccountService, Depends(get_account_service)],
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> dict[str, object]:
    try:
        start = _utc_naive(start_at) if start_at is not None else None
        end = _utc_naive(end_at) if end_at is not None else None
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail="ledger date bounds must include a UTC offset",
        ) from error
    if start is not None and end is not None and start > end:
        raise HTTPException(status_code=422, detail="start_at must not be after end_at")

    try:
        entries = service.get_ledger_for_user(
            owner_user_id=user.id,
            start_at=start,
            end_at=end,
            limit=limit,
            offset=offset,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail="account not found") from error
    return {
        "items": [
            {
                "entry_id": entry.entry_id,
                "posted_at": _utc_isoformat(entry.posted_at),
                "transaction_id": entry.transaction_id,
                "account_id": entry.account_id,
                "entry_type": entry.entry_type,
                "amount": entry.amount,
            }
            for entry in entries
        ],
        "limit": limit,
        "offset": offset,
    }


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a UTC offset")
    return value.astimezone(UTC).replace(tzinfo=None)


def _utc_isoformat(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value.isoformat(timespec="microseconds") + "Z"
