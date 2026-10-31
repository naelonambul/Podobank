"""Explainable ranking of public loan snapshots against synthetic profiles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import Connection

from podobank.catalog import ProductSnapshot
from podobank.db import Database
from podobank.events import append_event
from podobank.loans import (
    LoanResourceNotFound,
    complete_idempotent_request,
    reserve_idempotent_request,
)

MAX_RECOMMENDATION_CANDIDATES = 500
INCOME_BANDS = {"low", "middle", "high"}
EMPLOYMENT_CATEGORIES = {"employee", "self_employed", "student", "unemployed"}
CREDIT_SCORE_BANDS = ("fair", "good", "very_good", "excellent")
CRITERIA_ORDER = (
    "requestedAmount",
    "desiredTerm",
    "incomeBand",
    "employmentCategory",
    "creditScoreBand",
)


@dataclass(frozen=True)
class RecommendationProfile:
    requested_amount_won: int
    desired_term_months: int
    income_band: str | None = None
    employment_category: str | None = None
    credit_score_band: str | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.requested_amount_won, bool)
            or not isinstance(self.requested_amount_won, int)
            or not 1 <= self.requested_amount_won <= (1 << 64) - 1
        ):
            raise ValueError("requested_amount_won must be positive")
        if (
            isinstance(self.desired_term_months, bool)
            or not isinstance(self.desired_term_months, int)
            or not 1 <= self.desired_term_months <= 600
        ):
            raise ValueError("desired_term_months must be between 1 and 600")
        if self.income_band is not None and self.income_band not in INCOME_BANDS:
            raise ValueError("income_band is not a supported synthetic band")
        if (
            self.employment_category is not None
            and self.employment_category not in EMPLOYMENT_CATEGORIES
        ):
            raise ValueError("employment_category is not a supported synthetic category")
        if self.credit_score_band is not None and self.credit_score_band not in CREDIT_SCORE_BANDS:
            raise ValueError("credit_score_band is not a supported synthetic band")

    def to_payload(self) -> dict[str, Any]:
        return {
            "requestedAmountWon": self.requested_amount_won,
            "desiredTermMonths": self.desired_term_months,
            "incomeBand": self.income_band,
            "employmentCategory": self.employment_category,
            "creditScoreBand": self.credit_score_band,
            "simulation": True,
        }


@dataclass(frozen=True)
class RecommendationResult:
    recommendations: list[dict[str, Any]]
    excluded_products: list[dict[str, Any]]
    snapshot_ids: list[str]


class RecommendationCatalogTooLarge(RuntimeError):
    """Raised if the active catalog exceeds the bounded recommendation batch."""


def recommend(
    profile: RecommendationProfile,
    products: Sequence[ProductSnapshot],
    snapshot_id: str | None = None,
) -> RecommendationResult:
    candidates = [
        product for product in products if snapshot_id is None or product.snapshot_id == snapshot_id
    ]
    evaluated: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for product in candidates:
        item = _evaluate(profile, product)
        if item["unmetCriteria"]:
            excluded.append(item)
        else:
            evaluated.append(item)

    evaluated.sort(key=_ranking_key)
    excluded.sort(key=_ranking_key)
    return RecommendationResult(
        recommendations=evaluated,
        excluded_products=excluded,
        snapshot_ids=sorted(product.snapshot_id for product in candidates),
    )


def create_recommendation(
    database: Database,
    *,
    partner_id: str,
    profile: RecommendationProfile,
    snapshot_id: str | None,
    idempotency_key: str,
    freshness_interval_seconds: int = 604800,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    request_data = {"profile": profile.to_payload(), "snapshotId": snapshot_id}
    with database.transaction() as connection:
        replay = reserve_idempotent_request(
            database,
            connection,
            partner_id=partner_id,
            idempotency_key=idempotency_key,
            operation_type="loan.recommendation",
            request=request_data,
            created_at=now,
        )
        if replay is not None:
            return replay

        if snapshot_id is not None:
            row = database.catalog_snapshots.get_by_id(connection, snapshot_id)
            if row is None:
                raise LoanResourceNotFound("The loan-product snapshot was not found.")
            rows = [row]
        else:
            database.catalog_snapshots.acquire_writer_lock(connection)
            high_water = database.catalog_snapshots.latest_created_at(connection)
            rows = (
                database.catalog_snapshots.list_current(
                    connection,
                    high_water_created_at=high_water,
                    limit=MAX_RECOMMENDATION_CANDIDATES + 1,
                )
                if high_water is not None
                else []
            )
            if len(rows) > MAX_RECOMMENDATION_CANDIDATES:
                raise RecommendationCatalogTooLarge(
                    "The active product catalog exceeds the recommendation limit."
                )

        products = [_product_from_row(row) for row in rows]
        result = recommend(profile, products, snapshot_id)
        freshness = _freshness_by_source(
            database,
            connection,
            products,
            now=now,
            interval_seconds=freshness_interval_seconds,
        )
        for item in result.recommendations + result.excluded_products:
            source_id = str(item["productRef"]).partition(":")[0]
            item["sourceFreshness"] = freshness.get(source_id, "unknown")

        recommendation_id = str(uuid4())
        correlation_id = str(uuid4())
        event_data = {
            "recommendationId": recommendation_id,
            "profile": profile.to_payload(),
            "requestedSnapshotId": snapshot_id,
            "catalogSnapshotIds": result.snapshot_ids,
            "recommendations": result.recommendations,
            "excludedProducts": result.excluded_products,
            "simulation": True,
        }
        entity_refs = {"recommendationId": recommendation_id}
        if snapshot_id is not None:
            entity_refs["snapshotId"] = snapshot_id
        event = append_event(
            database,
            event_type="loan.recommendation.generated",
            entity_refs=entity_refs,
            correlation_id=correlation_id,
            data=event_data,
            connection=connection,
            occurred_at=now,
        )
        response = {
            "recommendationId": recommendation_id,
            "catalogSnapshotIds": result.snapshot_ids,
            "recommendations": result.recommendations,
            "excludedProducts": result.excluded_products,
            "correlationId": correlation_id,
            "eventIds": [event.event_id],
            "simulation": True,
        }
        complete_idempotent_request(
            database,
            connection,
            partner_id=partner_id,
            idempotency_key=idempotency_key,
            response=response,
        )
        return response


def _evaluate(profile: RecommendationProfile, product: ProductSnapshot) -> dict[str, Any]:
    facts = product.facts
    matched: list[str] = []
    unmet: list[str] = []
    unknown: list[str] = []
    checks = {
        "requestedAmount": _check_range(
            profile.requested_amount_won,
            facts.get("amountMinimumWon"),
            facts.get("amountMaximumWon"),
        ),
        "desiredTerm": _check_range(
            profile.desired_term_months,
            facts.get("termMinimumMonths"),
            facts.get("termMaximumMonths"),
        ),
        "incomeBand": _check_allowed(
            profile.income_band, facts.get("eligibleIncomeBands"), INCOME_BANDS
        ),
        "employmentCategory": _check_allowed(
            profile.employment_category,
            facts.get("eligibleEmploymentCategories"),
            EMPLOYMENT_CATEGORIES,
        ),
        "creditScoreBand": _check_credit_score(
            profile.credit_score_band,
            facts.get("minimumCreditScoreBand"),
            facts.get("eligibleCreditScoreBands"),
        ),
    }
    for criterion in CRITERIA_ORDER:
        status = checks[criterion]
        if status == "match":
            matched.append(criterion)
        elif status == "conflict":
            unmet.append(criterion)
        else:
            unknown.append(criterion)
    if product.source_status != "active":
        unmet.append("productAvailability")

    minimum_rate = _known_rate(facts.get("rateMinimumPercent"))
    maximum_rate = _known_rate(facts.get("rateMaximumPercent"))
    return {
        "snapshotId": product.snapshot_id,
        "productRef": product.product_ref,
        "institutionName": product.institution_name,
        "productName": product.product_name,
        "productCategory": product.product_category,
        "matchCriteria": matched,
        "unmetCriteria": unmet,
        "unknownCriteria": unknown,
        "publishedRateRangePercent": {
            "minimum": minimum_rate,
            "maximum": maximum_rate,
        },
        "facts": product.facts,
        "factAvailability": _fact_availability(product.facts),
        "sourceUrl": product.source_url,
        "retrievedAt": _format_time(product.retrieved_at),
        "effectiveDate": product.effective_date.isoformat()
        if product.effective_date is not None
        else None,
        "sourceStatus": product.source_status,
    }


def _check_range(requested: int, minimum_value: Any, maximum_value: Any) -> str:
    minimum = _known_integer(minimum_value)
    maximum = _known_integer(maximum_value)
    if minimum is None and maximum is None:
        return "unknown"
    if minimum is not None and maximum is not None and minimum > maximum:
        return "unknown"
    if minimum is not None and requested < minimum:
        return "conflict"
    if maximum is not None and requested > maximum:
        return "conflict"
    return "match"


def _check_allowed(profile_value: str | None, allowed_value: Any, known_values: set[str]) -> str:
    if profile_value is None or not isinstance(allowed_value, list) or not allowed_value:
        return "unknown"
    if any(not isinstance(value, str) or value not in known_values for value in allowed_value):
        return "unknown"
    return "match" if profile_value in allowed_value else "conflict"


def _check_credit_score(profile_value: str | None, minimum_value: Any, eligible_value: Any) -> str:
    if profile_value is None:
        return "unknown"
    if isinstance(eligible_value, list) and eligible_value:
        if any(
            not isinstance(value, str) or value not in CREDIT_SCORE_BANDS
            for value in eligible_value
        ):
            return "unknown"
        return "match" if profile_value in eligible_value else "conflict"
    if not isinstance(minimum_value, str) or minimum_value not in CREDIT_SCORE_BANDS:
        return "unknown"
    return (
        "match"
        if CREDIT_SCORE_BANDS.index(profile_value) >= CREDIT_SCORE_BANDS.index(minimum_value)
        else "conflict"
    )


def _ranking_key(item: Mapping[str, Any]) -> tuple[Any, ...]:
    rate = item["publishedRateRangePercent"]["minimum"]
    return (
        -len(item["matchCriteria"]),
        rate is None,
        rate if rate is not None else 0,
        str(item["institutionName"]).casefold(),
        str(item["productRef"]).casefold(),
        str(item["snapshotId"]),
    )


def _known_integer(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _known_rate(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return float(value)
    return None


def _fact_availability(facts: Mapping[str, Any]) -> dict[str, str]:
    return {
        key: "unknown" if value is None or value == [] else "published"
        for key, value in facts.items()
    }


def _product_from_row(row: Mapping[str, Any]) -> ProductSnapshot:
    return ProductSnapshot(
        product_ref=str(row["product_ref"]),
        institution_name=str(row["institution_name"]),
        product_name=str(row["product_name"]),
        product_category=str(row["product_category"]),
        facts=cast(dict[str, Any], row["facts"]),
        source_url=str(row["source_url"]),
        retrieved_at=cast(datetime, row["retrieved_at"]),
        effective_date=row["effective_date"],
        source_status=str(row["source_status"]),
        snapshot_id=str(row["snapshot_id"]),
    )


def _freshness_by_source(
    database: Database,
    connection: Connection,
    products: Sequence[ProductSnapshot],
    *,
    now: datetime,
    interval_seconds: int,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for source_id in {product.product_ref.partition(":")[0] for product in products}:
        health = database.catalog_refresh_state.health(connection, source_id)
        if health is None or health["last_completed_at"] is None:
            freshness = "unknown"
        elif health["last_error"] is not None or (
            now - health["last_completed_at"] > timedelta(seconds=interval_seconds)
        ):
            freshness = "stale"
        else:
            freshness = "current"
        result[source_id] = freshness
    return result


def _format_time(value: datetime) -> str:
    normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return normalized.isoformat().replace("+00:00", "Z")
