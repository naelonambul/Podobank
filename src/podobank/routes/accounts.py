"""Synthetic account reads, deposits, and withdrawals."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from podobank.auth import authenticate_request
from podobank.db import Database
from podobank.ledger import (
    MAX_TRANSACTION_AMOUNT_WON,
    AccountNotFound,
    IdempotencyConflict,
    Ledger,
    OperationResult,
)

router = APIRouter(prefix="/v1/accounts", tags=["Accounts"])


class AmountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_won: StrictInt = Field(alias="amountWon", gt=0, le=MAX_TRANSACTION_AMOUNT_WON)


def _respond(result: OperationResult) -> dict[str, Any]:
    if result.error_code is not None:
        body = result.body
        raise HTTPException(
            status_code=result.status_code,
            detail={
                "code": result.error_code,
                "message": result.error_message or "The operation was rejected.",
                "operationId": body["operationId"],
                "correlationId": body["correlationId"],
                "eventIds": body["eventIds"],
            },
        )
    return result.body


def _ledger(request: Request, partner_id: str) -> Ledger:
    return Ledger(request.app.state.database, partner_id)


@router.get(
    "/{account_id}",
    summary="Read a synthetic account balance",
    description="Return a fictional KRW account balance created inside a bootcamp sandbox.",
)
def get_account(
    account_id: str,
    request: Request,
    partner_id: Annotated[str, Depends(authenticate_request)],
) -> dict[str, object]:
    del partner_id
    database: Database = request.app.state.database
    with database.engine.connect() as connection:
        account = database.accounts.get(connection, account_id)
    if account is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "The synthetic account was not found."},
        )
    return {
        "accountId": account.account_id,
        "customerId": account.customer_id,
        "balanceWon": account.balance_won,
        "currency": account.currency,
        "simulation": True,
    }


@router.post(
    "/{account_id}/deposits",
    summary="Simulate a deposit",
    description=(
        "Add whole Korean won to a synthetic account. Send an Idempotency-Key header "
        "to safely retry the same request."
    ),
)
def deposit(
    account_id: str,
    body: AmountRequest,
    request: Request,
    partner_id: Annotated[str, Depends(authenticate_request)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> dict[str, Any]:
    try:
        result = _ledger(request, partner_id).deposit(account_id, body.amount_won, idempotency_key)
    except AccountNotFound as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": str(error)},
        ) from error
    except IdempotencyConflict as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "idempotency_conflict", "message": str(error)},
        ) from error
    return _respond(result)


@router.post(
    "/{account_id}/withdrawals",
    summary="Simulate a withdrawal",
    description=(
        "Subtract whole Korean won from a synthetic account. Insufficient-funds attempts "
        "are recorded as rejected transaction events without changing the balance."
    ),
)
def withdraw(
    account_id: str,
    body: AmountRequest,
    request: Request,
    partner_id: Annotated[str, Depends(authenticate_request)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> dict[str, Any]:
    try:
        result = _ledger(request, partner_id).withdraw(account_id, body.amount_won, idempotency_key)
    except AccountNotFound as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": str(error)},
        ) from error
    except IdempotencyConflict as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "idempotency_conflict", "message": str(error)},
        ) from error
    return _respond(result)
