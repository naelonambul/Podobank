"""Synthetic account-to-account transfer endpoint."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from podobank.auth import authenticate_request
from podobank.ledger import (
    MAX_TRANSACTION_AMOUNT_WON,
    AccountNotFound,
    IdempotencyConflict,
    Ledger,
    OperationResult,
)

router = APIRouter(prefix="/v1/transfers", tags=["Transfers"])


class TransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_account_id: str = Field(alias="sourceAccountId", min_length=1, max_length=80)
    destination_account_id: str = Field(alias="destinationAccountId", min_length=1, max_length=80)
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


@router.post(
    "",
    summary="Transfer simulated funds between accounts",
    description=(
        "Move whole Korean won between two synthetic accounts atomically. Rejected attempts "
        "are recorded without changing either balance."
    ),
)
def transfer(
    body: TransferRequest,
    request: Request,
    partner_id: Annotated[str, Depends(authenticate_request)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> dict[str, Any]:
    try:
        result = Ledger(request.app.state.database, partner_id).transfer(
            body.source_account_id,
            body.destination_account_id,
            body.amount_won,
            idempotency_key,
        )
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
