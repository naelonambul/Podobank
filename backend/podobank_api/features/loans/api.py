from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Engine

from podobank_api.database import get_engine
from podobank_api.features.auth.dependencies import get_current_customer, get_current_staff
from podobank_api.features.auth.service import AuthenticatedUser
from podobank_api.features.loans import service
from podobank_api.features.loans.service import LoanError

router = APIRouter(tags=["loans"])


class LoanProductResponse(BaseModel):
    id: int
    product_code: str
    name: str
    principal_krw: int
    term_months: int
    monthly_installment_krw: int


class LoanApplicationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(gt=0)


class LoanDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]


class RepaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_krw: int = Field(gt=0, le=1_000_000_000_000)


class InstallmentResponse(BaseModel):
    installment_number: int
    due_date: date
    amount_krw: int
    status: str
    paid_at: str | None


class LoanResponse(BaseModel):
    id: int
    status: str
    applied_at: str
    decided_at: str | None
    approved_at: str | None
    product_code: str
    product_name: str
    principal_krw: int
    term_months: int
    monthly_installment_krw: int
    installments: list[InstallmentResponse]


class StaffApplicationResponse(BaseModel):
    id: int
    user_id: int
    status: str
    applied_at: str
    name: str
    phone_number: str
    account_number: str
    product_name: str
    principal_krw: int
    term_months: int
    monthly_installment_krw: int


class LoanDecisionResponse(BaseModel):
    loan_id: int
    status: str


class RepaymentResponse(BaseModel):
    loan_id: int
    amount_krw: int
    balance_krw: int


def _raise_loan_error(error: LoanError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.detail) from error


@router.get("/loan-products", response_model=list[LoanProductResponse])
def products(engine: Annotated[Engine, Depends(get_engine)]) -> list[LoanProductResponse]:
    return [LoanProductResponse.model_validate(row) for row in service.loan_products(engine)]


@router.post("/loans/applications", status_code=201)
def apply_for_loan(
    body: LoanApplicationRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_customer)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> dict[str, int | str]:
    try:
        loan_id = service.apply_for_loan(engine, user.id, body.product_id)
    except LoanError as error:
        _raise_loan_error(error)
    return {"loan_id": loan_id, "status": "pending"}


@router.get("/loans", response_model=list[LoanResponse])
def my_loans(
    user: Annotated[AuthenticatedUser, Depends(get_current_customer)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> list[LoanResponse]:
    return [LoanResponse.model_validate(row) for row in service.user_loans(engine, user.id)]


@router.get("/staff/loans/applications", response_model=list[StaffApplicationResponse])
def pending_applications(
    _staff: Annotated[AuthenticatedUser, Depends(get_current_staff)],
    engine: Annotated[Engine, Depends(get_engine)],
    query: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[StaffApplicationResponse]:
    rows = service.staff_pending_applications(engine, query, limit)
    return [StaffApplicationResponse.model_validate(row) for row in rows]


@router.post(
    "/staff/loans/applications/{loan_id}/decision",
    response_model=LoanDecisionResponse,
)
def decide_application(
    loan_id: int,
    body: LoanDecisionRequest,
    _staff: Annotated[AuthenticatedUser, Depends(get_current_staff)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> LoanDecisionResponse:
    try:
        result = service.decide_application(engine, loan_id, decision=body.decision)
    except LoanError as error:
        _raise_loan_error(error)
    return LoanDecisionResponse.model_validate(result)


@router.post("/loans/{loan_id}/repayments", response_model=RepaymentResponse)
def repay_loan(
    loan_id: int,
    body: RepaymentRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_customer)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> RepaymentResponse:
    try:
        result = service.repay_overdue(engine, user.id, loan_id, body.amount_krw)
    except LoanError as error:
        _raise_loan_error(error)
    return RepaymentResponse.model_validate(result)
