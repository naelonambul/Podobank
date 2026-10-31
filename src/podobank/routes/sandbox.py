"""Synthetic sandbox provisioning endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from podobank.auth import authenticate_request
from podobank.sandbox import seed_sandbox

router = APIRouter(prefix="/v1/sandbox", tags=["Sandbox"])


class SeedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sandbox_id: str = Field(alias="sandboxId", min_length=1, max_length=80)
    customer_count: int = Field(alias="customerCount", ge=1, le=100)
    merchant_count: int = Field(alias="merchantCount", ge=1, le=100)


@router.post(
    "/seed",
    summary="Create or reuse synthetic sandbox records",
    description=(
        "Provision deterministic fictional customers, accounts, and merchants. "
        "Repeating the same partner and sandbox ID reuses the same records."
    ),
)
def create_sandbox_seed(
    body: SeedRequest,
    request: Request,
    partner_id: Annotated[str, Depends(authenticate_request)],
) -> dict[str, object]:
    try:
        return seed_sandbox(
            request.app.state.database,
            partner_id=partner_id,
            sandbox_id=body.sandbox_id,
            customer_count=body.customer_count,
            merchant_count=body.merchant_count,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_request", "message": str(error)},
        ) from error
