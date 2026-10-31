"""Current and historical public loan-product snapshots."""

from __future__ import annotations

from datetime import UTC
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from podobank.auth import authenticate_request
from podobank.catalog import InvalidProductCursor, read_product_page

router = APIRouter(prefix="/v1/loan-products", tags=["Loan products"])


@router.get(
    "",
    summary="Read published loan-product snapshots",
    description=(
        "Read the latest public catalog snapshots or their history. Each page cursor keeps "
        "the initial catalog high-water view stable while later refreshes are published. "
        "Unavailable product terms remain unknown; this catalog is not a bank quote."
    ),
)
def get_loan_products(
    request: Request,
    partner_id: Annotated[str, Depends(authenticate_request)],
    product_ref: Annotated[
        str | None, Query(alias="productRef", min_length=1, max_length=160)
    ] = None,
    institution_name: Annotated[
        str | None, Query(alias="institutionName", min_length=1, max_length=160)
    ] = None,
    include_history: Annotated[bool | None, Query(alias="includeHistory")] = None,
    cursor: Annotated[str | None, Query(min_length=1, max_length=4096)] = None,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
) -> dict[str, Any]:
    del partner_id
    database = request.app.state.database
    try:
        with database.engine.connect() as connection:
            page = read_product_page(
                database,
                connection,
                product_ref=product_ref,
                institution_name=institution_name,
                include_history=include_history,
                cursor=cursor,
                limit=limit,
                freshness_interval_seconds=(
                    request.app.state.settings.catalog_refresh_interval_seconds
                ),
            )
    except InvalidProductCursor as error:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_cursor", "message": str(error)},
        ) from error

    high_water = page.high_water_created_at
    if high_water is not None:
        high_water = (
            high_water.replace(tzinfo=UTC)
            if high_water.tzinfo is None
            else high_water.astimezone(UTC)
        )
    return {
        "items": page.items,
        "nextCursor": page.next_cursor,
        "highWaterCreatedAt": (
            high_water.isoformat().replace("+00:00", "Z") if high_water is not None else None
        ),
    }
