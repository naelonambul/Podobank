from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Engine

from podobank_api.database import get_engine
from podobank_api.features.auth.dependencies import get_current_customer
from podobank_api.features.auth.service import AuthenticatedUser
from podobank_api.features.transactions import service
from podobank_api.features.transactions.service import TransactionError

router = APIRouter(tags=["transactions"])


class TransactionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_krw: int = Field(gt=0, le=1_000_000_000_000)
    memo: str = Field(default="", max_length=120)


class TransferRequest(TransactionRequest):
    recipient_account_number: str = Field(min_length=8, max_length=20)


class TransactionResult(BaseModel):
    transaction_id: str
    balance_krw: int


class TransactionEntry(BaseModel):
    transaction_id: str
    entry_type: str
    amount_krw: int
    counterparty_account_number: str | None
    memo: str
    created_at: str


class Recipient(BaseModel):
    user_id: int
    name: str
    phone_number_masked: str
    account_number: str


def _raise_transaction_error(error: TransactionError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.detail) from error


@router.post("/accounts/me/deposits", response_model=TransactionResult)
def deposit(
    body: TransactionRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_customer)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> TransactionResult:
    try:
        result = service.deposit(engine, user.id, body.amount_krw, body.memo)
    except TransactionError as error:
        _raise_transaction_error(error)
    return TransactionResult.model_validate(result)


@router.post("/accounts/me/withdrawals", response_model=TransactionResult)
def withdraw(
    body: TransactionRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_customer)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> TransactionResult:
    try:
        result = service.withdraw(engine, user.id, body.amount_krw, body.memo)
    except TransactionError as error:
        _raise_transaction_error(error)
    return TransactionResult.model_validate(result)


@router.post("/accounts/me/transfers", response_model=TransactionResult)
def transfer(
    body: TransferRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_customer)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> TransactionResult:
    try:
        result = service.transfer(
            engine,
            user.id,
            body.recipient_account_number,
            body.amount_krw,
            body.memo,
        )
    except TransactionError as error:
        _raise_transaction_error(error)
    return TransactionResult.model_validate(result)


@router.get("/accounts/me/transactions", response_model=list[TransactionEntry])
def history(
    user: Annotated[AuthenticatedUser, Depends(get_current_customer)],
    engine: Annotated[Engine, Depends(get_engine)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[TransactionEntry]:
    entries = service.transaction_history(engine, user.id, limit=limit, offset=offset)
    return [TransactionEntry.model_validate(entry) for entry in entries]


@router.get("/recipients", response_model=list[Recipient])
def search_recipients(
    user: Annotated[AuthenticatedUser, Depends(get_current_customer)],
    engine: Annotated[Engine, Depends(get_engine)],
    query: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[Recipient]:
    found = service.recipients(engine, user.id, query, limit)
    return [Recipient.model_validate(row) for row in found]
