"""Lease-coordinated immutable catalog refreshes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol, cast
from uuid import uuid4

from podobank.catalog import ProductSnapshot
from podobank.db import Database

REFRESH_LEASE_DURATION = timedelta(minutes=15)


class CatalogSource(Protocol):
    institution_id: str

    def fetch_products(self, retrieved_at: datetime) -> list[ProductSnapshot]: ...


@dataclass(frozen=True)
class RefreshResult:
    snapshots_saved: int = 0
    retired_products: int = 0
    source_failures: dict[str, str] = field(default_factory=dict)
    skipped_in_progress: int = 0


def refresh_catalog(
    database: Database,
    sources: Sequence[CatalogSource],
    *,
    now: datetime | None = None,
    lease_owner: str | None = None,
) -> RefreshResult:
    retrieved_at = now or datetime.now(UTC)
    if retrieved_at.tzinfo is None:
        raise ValueError("refresh time must be timezone-aware")
    retrieved_at = retrieved_at.astimezone(UTC)
    owner = lease_owner or str(uuid4())
    snapshots_saved = 0
    retired_products = 0
    skipped_in_progress = 0
    source_failures: dict[str, str] = {}

    for source in sources:
        if not source.institution_id:
            raise ValueError("catalog source institution_id must not be empty")
        with database.transaction() as connection:
            acquired = database.catalog_refresh_state.acquire(
                connection,
                institution_id=source.institution_id,
                owner=owner,
                now=retrieved_at,
                expires_at=retrieved_at + REFRESH_LEASE_DURATION,
            )
        if not acquired:
            skipped_in_progress += 1
            continue

        try:
            products = source.fetch_products(retrieved_at)
            _validate_products(source, products)
            source_snapshots_saved = 0
            source_retired_products = 0
            with database.transaction() as connection:
                database.catalog_snapshots.acquire_writer_lock(connection)
                latest_created_at = database.catalog_snapshots.latest_created_at(connection)
                created_at = _next_created_at(retrieved_at, latest_created_at)
                latest_products = database.catalog_snapshots.latest_for_institution(
                    connection, _institution_name(products)
                )
                current_by_ref = {
                    row["product_ref"]: row
                    for row in latest_products
                    if row["source_status"] == "active"
                }
                incoming_refs = {product.product_ref for product in products}
                for product in products:
                    database.catalog_snapshots.save(
                        connection,
                        snapshot_id=product.snapshot_id,
                        product_ref=product.product_ref,
                        institution_name=product.institution_name,
                        product_name=product.product_name,
                        product_category=product.product_category,
                        facts=product.facts,
                        source_url=product.source_url,
                        retrieved_at=product.retrieved_at,
                        effective_date=product.effective_date,
                        source_status=product.source_status,
                        created_at=created_at,
                    )
                    created_at += timedelta(microseconds=1)
                    source_snapshots_saved += 1
                for product_ref, previous in current_by_ref.items():
                    if product_ref in incoming_refs:
                        continue
                    retired = replace(
                        _product_from_row(previous),
                        snapshot_id=str(uuid4()),
                        retrieved_at=retrieved_at,
                        source_status="retired",
                    )
                    database.catalog_snapshots.save(
                        connection,
                        snapshot_id=retired.snapshot_id,
                        product_ref=retired.product_ref,
                        institution_name=retired.institution_name,
                        product_name=retired.product_name,
                        product_category=retired.product_category,
                        facts=retired.facts,
                        source_url=retired.source_url,
                        retrieved_at=retired.retrieved_at,
                        effective_date=retired.effective_date,
                        source_status=retired.source_status,
                        created_at=created_at,
                    )
                    created_at += timedelta(microseconds=1)
                    source_snapshots_saved += 1
                    source_retired_products += 1
                database.catalog_refresh_state.complete(
                    connection,
                    institution_id=source.institution_id,
                    owner=owner,
                    completed_at=retrieved_at,
                    error=None,
                )
            snapshots_saved += source_snapshots_saved
            retired_products += source_retired_products
        except Exception as error:
            message = _safe_error_message(error)
            source_failures[source.institution_id] = message
            with database.transaction() as connection:
                database.catalog_refresh_state.complete(
                    connection,
                    institution_id=source.institution_id,
                    owner=owner,
                    completed_at=retrieved_at,
                    error=message,
                )

    return RefreshResult(
        snapshots_saved=snapshots_saved,
        retired_products=retired_products,
        source_failures=source_failures,
        skipped_in_progress=skipped_in_progress,
    )


def _validate_products(source: CatalogSource, products: list[ProductSnapshot]) -> None:
    if not products:
        raise ValueError("source returned no loan products")
    refs = [product.product_ref for product in products]
    if len(refs) != len(set(refs)):
        raise ValueError("source returned duplicate product references")
    if any(product.source_status != "active" for product in products):
        raise ValueError("source adapters must return active products")
    if len({product.institution_name for product in products}) != 1:
        raise ValueError("source returned inconsistent institution names")
    if any(not product.product_ref.startswith(f"{source.institution_id}:") for product in products):
        raise ValueError("source returned a product reference for another institution")


def _institution_name(products: list[ProductSnapshot]) -> str:
    return products[0].institution_name


def _next_created_at(now: datetime, latest: datetime | None) -> datetime:
    if latest is None or now > latest:
        return now
    return latest + timedelta(microseconds=1)


def _product_from_row(row: dict[str, object]) -> ProductSnapshot:
    return ProductSnapshot(
        product_ref=str(row["product_ref"]),
        institution_name=str(row["institution_name"]),
        product_name=str(row["product_name"]),
        product_category=str(row["product_category"]),
        facts=cast(dict[str, Any], row["facts"]),
        source_url=str(row["source_url"]),
        retrieved_at=cast(datetime, row["retrieved_at"]),
        effective_date=cast(date | None, row["effective_date"]),
        source_status=str(row["source_status"]),
    )


def _safe_error_message(error: Exception) -> str:
    message = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
    return message[:500]
