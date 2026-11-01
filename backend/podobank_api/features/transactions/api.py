from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from podobank_api.features.auth.dependencies import require_customer
from podobank_api.features.auth.models import AuthenticatedUser
from podobank_api.features.transactions.schemas import AmountRequest, TransferRequest
from podobank_api.features.transactions.service import (
    AccountNotFoundError,
    InsufficientFundsError,
    InvalidAmountError,
    RecipientNotFoundError,
    SelfTransferError,
    TransactionResult,
    TransactionService,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


def get_transaction_service(request: Request) -> TransactionService:
    return request.app.state.transaction_service


def _response(result: TransactionResult) -> dict[str, int | str]:
    return {
        "transaction_id": result.transaction_id,
        "account_id": result.account_id,
        "amount": result.amount,
        "balance": result.balance,
    }


def _raise_transaction_http_error(error: Exception) -> None:
    if isinstance(error, InsufficientFundsError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "insufficient_funds", "message": "account balance is insufficient"},
        ) from error
    if isinstance(error, InvalidAmountError):
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_amount", "message": "amount must be a positive integer"},
        ) from error
    if isinstance(error, RecipientNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "recipient_not_found", "message": "recipient account not found"},
        ) from error
    if isinstance(error, SelfTransferError):
        raise HTTPException(
            status_code=422,
            detail={"code": "self_transfer", "message": "cannot transfer to the same account"},
        ) from error
    if isinstance(error, AccountNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="account not found",
        ) from error
    raise error


@router.post("/deposit")
def deposit(
    request: AmountRequest,
    user: Annotated[AuthenticatedUser, Depends(require_customer)],
    service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> dict[str, int | str]:
    try:
        return _response(service.deposit(user_id=user.id, amount=request.amount))
    except (AccountNotFoundError, InvalidAmountError) as error:
        _raise_transaction_http_error(error)


@router.post("/withdrawal")
def withdraw(
    request: AmountRequest,
    user: Annotated[AuthenticatedUser, Depends(require_customer)],
    service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> dict[str, int | str]:
    try:
        return _response(service.withdraw(user_id=user.id, amount=request.amount))
    except (AccountNotFoundError, InsufficientFundsError, InvalidAmountError) as error:
        _raise_transaction_http_error(error)


@router.post("/transfer")
def transfer(
    request: TransferRequest,
    user: Annotated[AuthenticatedUser, Depends(require_customer)],
    service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> dict[str, int | str]:
    try:
        result = service.transfer(
            user_id=user.id,
            destination_account_id=request.destination_account_id,
            amount=request.amount,
        )
        return _response(result)
    except (
        AccountNotFoundError,
        InsufficientFundsError,
        InvalidAmountError,
        RecipientNotFoundError,
        SelfTransferError,
    ) as error:
        _raise_transaction_http_error(error)
