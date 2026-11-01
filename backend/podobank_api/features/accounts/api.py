from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.engine import Engine

from podobank_api.database import get_engine
from podobank_api.features.accounts.service import get_account_for_user
from podobank_api.features.auth.dependencies import get_current_customer
from podobank_api.features.auth.service import AuthenticatedUser

router = APIRouter(tags=["accounts"])


class AccountResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_number: str
    balance_krw: int


@router.get("/accounts/me", response_model=AccountResponse)
def my_account(
    user: Annotated[AuthenticatedUser, Depends(get_current_customer)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> AccountResponse:
    account = get_account_for_user(engine, user.id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    return AccountResponse(
        account_number=str(account["account_number"]),
        balance_krw=int(account["balance_krw"]),
    )
