"""Synthetic sandbox provisioning endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from podobank.auth import authenticate_request
from podobank.ledger import Ledger
from podobank.sandbox import seed_sandbox
from podobank.scenarios import generate_scenario

router = APIRouter(prefix="/v1/sandbox", tags=["Sandbox"])


class SeedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sandbox_id: str = Field(alias="sandboxId", min_length=1, max_length=80)
    customer_count: int = Field(alias="customerCount", ge=1, le=100)
    merchant_count: int = Field(alias="merchantCount", ge=1, le=100)


class ScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sandbox_id: str = Field(alias="sandboxId", min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=40)
    count: StrictInt = Field(ge=1, le=100)
    seed: StrictInt = Field(ge=0, le=(1 << 63) - 1)


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


@router.post(
    "/generations",
    summary="Generate a reproducible synthetic activity scenario",
    description=(
        "Apply seeded deposits, withdrawals, and internal transfers to two synthetic "
        "sandbox accounts. Business values repeat for the same scenario name and seed; "
        "generated identifiers and timestamps vary."
    ),
)
def create_scenario(
    body: ScenarioRequest,
    request: Request,
    partner_id: Annotated[str, Depends(authenticate_request)],
) -> dict[str, object]:
    try:
        scenario = generate_scenario(body.name, body.count, body.seed)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_scenario", "message": str(error)},
        ) from error

    sandbox = seed_sandbox(
        request.app.state.database,
        partner_id=partner_id,
        sandbox_id=body.sandbox_id,
        customer_count=2,
        merchant_count=1,
    )
    account_ids = [customer["accountId"] for customer in sandbox["customers"]]
    correlation_id = str(uuid4())
    ledger = Ledger(request.app.state.database, partner_id)
    operations: list[dict[str, object]] = []
    event_ids: list[str] = []

    for index, generated in enumerate(scenario.operations):
        source_account_id = account_ids[generated.source_index]
        key = f"scenario-{correlation_id}-{index}"
        context = {"scenarioName": body.name, "scenarioSeed": body.seed}
        if generated.operation_type == "deposit":
            result = ledger.deposit(
                source_account_id,
                generated.amount_won,
                key,
                correlation_id=correlation_id,
                event_context=context,
            )
        elif generated.operation_type == "withdrawal":
            result = ledger.withdraw(
                source_account_id,
                generated.amount_won,
                key,
                correlation_id=correlation_id,
                event_context=context,
            )
        else:
            if generated.destination_index is None:
                raise RuntimeError("transfer scenario is missing its destination account")
            destination_account_id = account_ids[generated.destination_index]
            result = ledger.transfer(
                source_account_id,
                destination_account_id,
                generated.amount_won,
                key,
                correlation_id=correlation_id,
                event_context=context,
            )

        operation = {
            "operationType": generated.operation_type,
            "amountWon": generated.amount_won,
            "sourceIndex": generated.source_index,
            "sourceAccountId": source_account_id,
            "operationId": result.body["operationId"],
            "status": result.body["status"],
            "eventIds": result.body["eventIds"],
            "simulation": True,
        }
        if generated.destination_index is not None:
            operation["destinationIndex"] = generated.destination_index
            operation["destinationAccountId"] = account_ids[generated.destination_index]
        operations.append(operation)
        event_ids.extend(str(event_id) for event_id in result.body["eventIds"])

    return {
        "scenarioId": str(uuid4()),
        "sandboxId": body.sandbox_id,
        "name": scenario.name,
        "seed": scenario.seed,
        "count": scenario.count,
        "correlationId": correlation_id,
        "operations": operations,
        "eventIds": event_ids,
        "simulation": True,
    }
