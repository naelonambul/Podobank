"""Synthetic loan recommendations and simulated application endpoints."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from podobank.auth import authenticate_request
from podobank.ledger import MAX_TRANSACTION_AMOUNT_WON, IdempotencyConflict
from podobank.loans import MAX_LOAN_TERM_MONTHS, LoanResourceNotFound, create_simulated_loan
from podobank.recommendations import (
    RecommendationCatalogTooLarge,
    RecommendationProfile,
    create_recommendation,
)

router = APIRouter(tags=["Loans"])


class RecommendationProfileBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_amount_won: StrictInt = Field(
        alias="requestedAmountWon", gt=0, le=MAX_TRANSACTION_AMOUNT_WON
    )
    desired_term_months: StrictInt = Field(alias="desiredTermMonths", ge=1, le=MAX_LOAN_TERM_MONTHS)
    income_band: Literal["low", "middle", "high"] | None = Field(default=None, alias="incomeBand")
    employment_category: Literal["employee", "self_employed", "student", "unemployed"] | None = (
        Field(default=None, alias="employmentCategory")
    )
    credit_score_band: Literal["fair", "good", "very_good", "excellent"] | None = Field(
        default=None, alias="creditScoreBand"
    )

    def to_domain(self) -> RecommendationProfile:
        return RecommendationProfile(
            requested_amount_won=self.requested_amount_won,
            desired_term_months=self.desired_term_months,
            income_band=self.income_band,
            employment_category=self.employment_category,
            credit_score_band=self.credit_score_band,
        )


class RecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: RecommendationProfileBody
    snapshot_id: str | None = Field(default=None, alias="snapshotId", min_length=1, max_length=36)


class LoanApplicationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str = Field(alias="customerId", min_length=1, max_length=36)
    account_id: str = Field(alias="accountId", min_length=1, max_length=36)
    snapshot_id: str = Field(alias="snapshotId", min_length=1, max_length=36)
    amount_won: StrictInt = Field(alias="amountWon", gt=0, le=MAX_TRANSACTION_AMOUNT_WON)
    term_months: StrictInt = Field(alias="termMonths", ge=1, le=MAX_LOAN_TERM_MONTHS)
    scenario_seed: StrictInt = Field(alias="scenarioSeed", ge=0, le=(1 << 63) - 1)


@router.post(
    "/v1/loan-recommendations",
    summary="Rank public loan products for a synthetic profile",
    description=(
        "Compare a fictional amount, term, income band, employment category, and credit-score "
        "band with public product facts. Known conflicts are excluded; unpublished facts stay "
        "unknown. The result is educational and is not an eligibility decision, quote, or advice. "
        "A supplied snapshotId replays the comparison against that exact catalog version."
    ),
)
def post_loan_recommendation(
    body: RecommendationRequest,
    request: Request,
    partner_id: Annotated[str, Depends(authenticate_request)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> dict[str, Any]:
    try:
        return create_recommendation(
            request.app.state.database,
            partner_id=partner_id,
            profile=body.profile.to_domain(),
            snapshot_id=body.snapshot_id,
            idempotency_key=idempotency_key,
            freshness_interval_seconds=request.app.state.settings.catalog_refresh_interval_seconds,
        )
    except LoanResourceNotFound as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": str(error)},
        ) from error
    except IdempotencyConflict as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "idempotency_conflict", "message": str(error)},
        ) from error
    except RecommendationCatalogTooLarge as error:
        raise HTTPException(
            status_code=503,
            detail={"code": "catalog_too_large", "message": str(error)},
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_request", "message": str(error)},
        ) from error


@router.post(
    "/v1/loans",
    summary="Create a simulated loan application",
    description=(
        "Record a fictional loan application against one exact product snapshot and synthetic "
        "customer account. The scenarioSeed deterministically selects a demo outcome: an even "
        "seed disburses and an odd seed rejects after published bounds are checked. A disbursement "
        "credits only the synthetic account. No real bank application or debt is created."
    ),
)
def post_simulated_loan(
    body: LoanApplicationRequest,
    request: Request,
    partner_id: Annotated[str, Depends(authenticate_request)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> dict[str, Any]:
    try:
        return create_simulated_loan(
            request.app.state.database,
            partner_id=partner_id,
            customer_id=body.customer_id,
            account_id=body.account_id,
            snapshot_id=body.snapshot_id,
            amount_won=body.amount_won,
            term_months=body.term_months,
            scenario_seed=body.scenario_seed,
            idempotency_key=idempotency_key,
        )
    except LoanResourceNotFound as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": str(error)},
        ) from error
    except IdempotencyConflict as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "idempotency_conflict", "message": str(error)},
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_request", "message": str(error)},
        ) from error
