from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from podobank_api.features.accounts.service import AccountService
from podobank_api.features.auth.dependencies import get_current_user
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
