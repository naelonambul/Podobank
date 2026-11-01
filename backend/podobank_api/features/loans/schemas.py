from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class LoanApplicationRequest(BaseModel):
    product_id: int = Field(strict=True, gt=0)


class LoanRepaymentRequest(BaseModel):
    amount: int = Field(strict=True, gt=0)


class LoanProductResponse(BaseModel):
    id: int
    code: str
    name: str
    principal_amount: int
    term_months: int
    monthly_installment: int


class LoanProductsResponse(BaseModel):
    items: list[LoanProductResponse]


class LoanRepaymentResponse(BaseModel):
    id: int
    installment_number: int
    due_date: date
    amount: int
    status: Literal["scheduled", "paid", "overdue"]
    processed_at: datetime | None
    paid_at: datetime | None


class LoanApplicationResponse(BaseModel):
    id: int
    product_id: int
    product_code: str
    product_name: str
    principal_amount: int
    term_months: int
    monthly_installment: int
    status: Literal["pending", "repaying", "rejected", "repaid"]
    created_at: datetime
    reviewed_at: datetime | None
    reviewed_by: int | None
    approved_at: datetime | None
    repayments: list[LoanRepaymentResponse] = Field(default_factory=list)


class LoanApplicationsResponse(BaseModel):
    items: list[LoanApplicationResponse]


class PendingLoanApplicationResponse(BaseModel):
    id: int
    user_id: int
    customer_name: str
    product_code: str
    product_name: str
    principal_amount: int
    term_months: int
    monthly_installment: int
    created_at: datetime


class PendingLoanApplicationsResponse(BaseModel):
    items: list[PendingLoanApplicationResponse]
    limit: int
    offset: int


class LoanReviewResponse(BaseModel):
    application_id: int
    status: Literal["repaying", "rejected"]
    repayment_count: int = 0


class LoanRepaymentResultResponse(BaseModel):
    application_id: int
    status: Literal["repaying", "repaid"]
    amount: int
    balance: int
    paid_installments: int
