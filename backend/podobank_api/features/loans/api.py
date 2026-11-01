from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from podobank_api.features.auth.dependencies import require_bank_employee, require_customer
from podobank_api.features.auth.models import AuthenticatedUser
from podobank_api.features.loans.schemas import (
    LoanApplicationRequest,
    LoanApplicationResponse,
    LoanApplicationsResponse,
    LoanProductsResponse,
    LoanRepaymentRequest,
    LoanRepaymentResultResponse,
    LoanReviewResponse,
    PendingLoanApplicationsResponse,
)
from podobank_api.features.loans.service import (
    ActiveLoanExistsError,
    InvalidLoanAmountError,
    LoanAccountNotFoundError,
    LoanApplicationNotFoundError,
    LoanApplicationNotPendingError,
    LoanBalanceLimitError,
    LoanInsufficientFundsError,
    LoanNotRepayingError,
    LoanProductNotFoundError,
    LoanService,
    NoOverdueInstallmentsError,
)

router = APIRouter(prefix="/loans", tags=["loans"])


def get_loan_service(request: Request) -> LoanService:
    return request.app.state.loan_service


@router.get("/products", response_model=LoanProductsResponse)
def list_products(
    _user: Annotated[AuthenticatedUser, Depends(require_customer)],
    service: Annotated[LoanService, Depends(get_loan_service)],
) -> dict[str, object]:
    return {"items": service.list_products()}


@router.post(
    "/applications",
    response_model=LoanApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
def apply_for_loan(
    request: LoanApplicationRequest,
    user: Annotated[AuthenticatedUser, Depends(require_customer)],
    service: Annotated[LoanService, Depends(get_loan_service)],
) -> dict[str, object]:
    try:
        application = service.apply(user_id=user.id, product_id=request.product_id)
    except ActiveLoanExistsError as error:
        raise _http_error(
            409,
            "active_loan_exists",
            "customer already has an active loan",
        ) from error
    except LoanProductNotFoundError as error:
        raise _http_error(404, "product_not_found", "loan product not found") from error
    except LoanAccountNotFoundError as error:
        raise _http_error(404, "account_not_found", "account not found") from error
    return _application_response(application, [])


@router.get("/me", response_model=LoanApplicationsResponse)
def list_my_loans(
    user: Annotated[AuthenticatedUser, Depends(require_customer)],
    service: Annotated[LoanService, Depends(get_loan_service)],
) -> dict[str, object]:
    return {
        "items": [
            _application_response(application, application["repayments"])
            for application in service.customer_applications(user_id=user.id)
        ]
    }


@router.get("/pending", response_model=PendingLoanApplicationsResponse)
def list_pending_loans(
    _employee: Annotated[AuthenticatedUser, Depends(require_bank_employee)],
    service: Annotated[LoanService, Depends(get_loan_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> dict[str, object]:
    return {
        "items": service.pending_applications(limit=limit, offset=offset),
        "limit": limit,
        "offset": offset,
    }


@router.post("/{application_id}/approve", response_model=LoanReviewResponse)
def approve_loan(
    application_id: int,
    employee: Annotated[AuthenticatedUser, Depends(require_bank_employee)],
    service: Annotated[LoanService, Depends(get_loan_service)],
) -> dict[str, object]:
    try:
        repayment_count = service.approve(
            application_id=application_id,
            employee_id=employee.id,
        )
    except LoanApplicationNotFoundError as error:
        raise _http_error(404, "application_not_found", "loan application not found") from error
    except LoanApplicationNotPendingError as error:
        raise _http_error(
            409,
            "application_not_pending",
            "loan application is not pending",
        ) from error
    except LoanAccountNotFoundError as error:
        raise _http_error(404, "account_not_found", "account not found") from error
    except LoanBalanceLimitError as error:
        raise _http_error(
            409,
            "balance_limit",
            "resulting account balance exceeds the limit",
        ) from error
    return {
        "application_id": application_id,
        "status": "repaying",
        "repayment_count": repayment_count,
    }


@router.post("/{application_id}/reject", response_model=LoanReviewResponse)
def reject_loan(
    application_id: int,
    employee: Annotated[AuthenticatedUser, Depends(require_bank_employee)],
    service: Annotated[LoanService, Depends(get_loan_service)],
) -> dict[str, object]:
    try:
        service.reject(application_id=application_id, employee_id=employee.id)
    except LoanApplicationNotFoundError as error:
        raise _http_error(404, "application_not_found", "loan application not found") from error
    except LoanApplicationNotPendingError as error:
        raise _http_error(
            409,
            "application_not_pending",
            "loan application is not pending",
        ) from error
    return {"application_id": application_id, "status": "rejected", "repayment_count": 0}


@router.post(
    "/me/{application_id}/repayments",
    response_model=LoanRepaymentResultResponse,
)
def repay_overdue(
    application_id: int,
    request: LoanRepaymentRequest,
    user: Annotated[AuthenticatedUser, Depends(require_customer)],
    service: Annotated[LoanService, Depends(get_loan_service)],
) -> dict[str, object]:
    try:
        result = service.repay_overdue(
            user_id=user.id,
            application_id=application_id,
            amount=request.amount,
        )
    except LoanApplicationNotFoundError as error:
        raise _http_error(404, "application_not_found", "loan application not found") from error
    except LoanNotRepayingError as error:
        raise _http_error(409, "loan_not_repaying", "loan is not accepting repayments") from error
    except NoOverdueInstallmentsError as error:
        raise _http_error(
            409,
            "no_overdue_installments",
            "loan has no overdue installments",
        ) from error
    except LoanInsufficientFundsError as error:
        raise _http_error(409, "insufficient_funds", "account balance is insufficient") from error
    except InvalidLoanAmountError as error:
        raise _http_error(
            422,
            "invalid_amount",
            "amount must cover whole overdue installments",
        ) from error
    except LoanAccountNotFoundError as error:
        raise _http_error(404, "account_not_found", "account not found") from error
    return {
        "application_id": result.application_id,
        "status": result.status,
        "amount": result.amount,
        "balance": result.balance,
        "paid_installments": result.paid_installments,
    }


def _application_response(
    application: dict[str, object],
    repayments: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "id": application["id"],
        "product_id": application["product_id"],
        "product_code": application["product_code"],
        "product_name": application["product_name"],
        "principal_amount": application["principal_amount"],
        "term_months": application["term_months"],
        "monthly_installment": application["monthly_installment"],
        "status": application["status"],
        "created_at": application["created_at"],
        "reviewed_at": application["reviewed_at"],
        "reviewed_by": application["reviewed_by"],
        "approved_at": application["approved_at"],
        "repayments": [
            {
                "id": repayment["id"],
                "installment_number": repayment["installment_number"],
                "due_date": repayment["due_date"],
                "amount": repayment["amount"],
                "status": repayment["status"],
                "processed_at": repayment["processed_at"],
                "paid_at": repayment["paid_at"],
            }
            for repayment in repayments
        ],
    }


def _http_error(code: int, error_code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=code,
        detail={"code": error_code, "message": message},
    )
