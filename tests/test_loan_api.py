from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from podobank.catalog import ProductSnapshot
from podobank.catalog_refresh import refresh_catalog
from podobank.recommendations import RecommendationProfile, recommend

PARTNER_ID = "loan-training-project"
PARTNER_KEY = "test-loan-partner-secret"
NOW = datetime(2026, 10, 31, tzinfo=UTC)


class FixtureCatalogSource:
    institution_id = "hana"

    def __init__(self, products: list[ProductSnapshot]) -> None:
        self.products = products

    def fetch_products(self, retrieved_at: datetime) -> list[ProductSnapshot]:
        return [
            replace(product, retrieved_at=retrieved_at, snapshot_id=str(uuid4()))
            for product in self.products
        ]


def product(
    product_ref: str,
    *,
    facts: dict[str, object] | None = None,
    institution_name: str = "Hana Bank",
) -> ProductSnapshot:
    return ProductSnapshot(
        product_ref=product_ref,
        institution_name=institution_name,
        product_name=f"Synthetic test product {product_ref.rsplit(':', 1)[-1]}",
        product_category="personal_credit",
        facts=facts or {},
        source_url="https://bank.example/public/catalog",
        retrieved_at=NOW,
        effective_date=None,
    )


def app_client(database_url: str) -> TestClient:
    from podobank.config import Settings
    from podobank.main import create_app

    settings = Settings(database_url=database_url, partner_keys={PARTNER_ID: PARTNER_KEY})
    return TestClient(create_app(database_url=database_url, settings=settings))


def seed_account(client: TestClient, sandbox_id: str) -> tuple[str, str]:
    response = client.post(
        "/v1/sandbox/seed",
        json={"sandboxId": sandbox_id, "customerCount": 1, "merchantCount": 1},
        headers={"Authorization": f"Bearer {PARTNER_KEY}"},
    )
    assert response.status_code == 200
    customer = response.json()["customers"][0]
    return customer["customerId"], customer["accountId"]


def test_recommendation_excludes_known_conflicts_and_ranks_unknowns_deterministically() -> None:
    profile = RecommendationProfile(
        requested_amount_won=250_000,
        desired_term_months=12,
        income_band="middle",
        employment_category="employee",
        credit_score_band="good",
    )
    common_facts: dict[str, object] = {
        "amountMaximumWon": 500_000,
        "termMinimumMonths": 6,
        "termMaximumMonths": 24,
        "eligibleIncomeBands": ["middle"],
        "eligibleEmploymentCategories": ["employee"],
        "minimumCreditScoreBand": "fair",
        "rateMinimumPercent": 3.5,
    }
    candidates = [
        product("hana:z-eligible", facts=common_facts),
        product(
            "hana:unknown",
            facts={
                "amountMaximumWon": None,
                "termMinimumMonths": None,
                "termMaximumMonths": None,
                "rateMinimumPercent": None,
            },
            institution_name="Woori Bank",
        ),
        product(
            "hana:conflict",
            facts={**common_facts, "amountMaximumWon": 100_000, "rateMinimumPercent": 2.0},
        ),
        product(
            "hana:term-conflict",
            facts={**common_facts, "termMaximumMonths": 6},
        ),
        product("hana:a-eligible", facts=common_facts),
        product("hana:higher-rate", facts={**common_facts, "rateMinimumPercent": 4.25}),
    ]

    result = recommend(profile, candidates)

    assert [item["productRef"] for item in result.recommendations] == [
        "hana:a-eligible",
        "hana:z-eligible",
        "hana:higher-rate",
        "hana:unknown",
    ]
    assert result.recommendations[0]["matchCriteria"] == [
        "requestedAmount",
        "desiredTerm",
        "incomeBand",
        "employmentCategory",
        "creditScoreBand",
    ]
    assert result.recommendations[-1]["unknownCriteria"] == [
        "requestedAmount",
        "desiredTerm",
        "incomeBand",
        "employmentCategory",
        "creditScoreBand",
    ]
    excluded = {item["productRef"]: item for item in result.excluded_products}
    assert excluded["hana:conflict"]["unmetCriteria"] == ["requestedAmount"]
    assert excluded["hana:term-conflict"]["unmetCriteria"] == ["desiredTerm"]


def test_recommendation_api_is_idempotent_and_records_exact_snapshot_ids(
    database_url: str,
) -> None:
    product_ref = f"hana:recommend-{uuid4()}"
    product_snapshot = product(
        product_ref,
        facts={"amountMaximumWon": 1_000_000, "rateMinimumPercent": 4.1},
        institution_name=f"Hana Recommendation {uuid4()}",
    )
    with app_client(database_url) as client:
        refresh_catalog(
            client.app.state.database,
            [FixtureCatalogSource([product_snapshot])],
            now=NOW,
            lease_owner=f"recommend-{uuid4()}",
        )
        with client.app.state.database.engine.connect() as connection:
            stored = connection.execute(
                text(
                    "SELECT snapshot_id FROM loan_product_snapshots "
                    "WHERE product_ref = :product_ref ORDER BY created_at DESC LIMIT 1"
                ),
                {"product_ref": product_ref},
            ).scalar_one()
        request_body = {
            "profile": {
                "requestedAmountWon": 300_000,
                "desiredTermMonths": 12,
                "incomeBand": "middle",
                "employmentCategory": "employee",
                "creditScoreBand": "good",
            },
            "snapshotId": stored,
        }
        headers = {
            "Authorization": f"Bearer {PARTNER_KEY}",
            "Idempotency-Key": f"recommend-{uuid4()}",
        }
        first = client.post("/v1/loan-recommendations", json=request_body, headers=headers)
        replay = client.post("/v1/loan-recommendations", json=request_body, headers=headers)
        changed = client.post(
            "/v1/loan-recommendations",
            json={
                **request_body,
                "profile": {**request_body["profile"], "requestedAmountWon": 400_000},
            },
            headers=headers,
        )
        personal_data = client.post(
            "/v1/loan-recommendations",
            json={**request_body, "fullName": "not accepted"},
            headers={
                "Authorization": f"Bearer {PARTNER_KEY}",
                "Idempotency-Key": f"personal-data-rejected-{uuid4()}",
            },
        )
        events = client.get(
            "/v1/events",
            params={
                "eventType": "loan.recommendation.generated",
                "correlationId": first.json()["correlationId"],
            },
            headers={"Authorization": f"Bearer {PARTNER_KEY}"},
        )

    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert first.json()["recommendations"][0]["snapshotId"] == stored
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "idempotency_conflict"
    assert personal_data.status_code == 400
    assert len(events.json()["items"]) == 1
    assert events.json()["items"][0]["eventType"] == "loan.recommendation.generated"
    assert events.json()["items"][0]["data"]["catalogSnapshotIds"] == [stored]


def test_recommendation_api_ranks_the_current_catalog(database_url: str) -> None:
    institution_name = f"Hana Current Catalog {uuid4()}"
    candidates = [
        product(
            f"hana:current-{index}-{uuid4()}",
            institution_name=institution_name,
            facts={
                "amountMaximumWon": 500_000,
                "termMinimumMonths": 6,
                "termMaximumMonths": 36,
                "rateMinimumPercent": 4.0 + index,
            },
        )
        for index in range(2)
    ]
    with app_client(database_url) as client:
        refresh_catalog(
            client.app.state.database,
            [FixtureCatalogSource(candidates)],
            now=NOW,
            lease_owner=f"current-catalog-{uuid4()}",
        )
        response = client.post(
            "/v1/loan-recommendations",
            json={
                "profile": {
                    "requestedAmountWon": 300_000,
                    "desiredTermMonths": 12,
                    "incomeBand": "middle",
                }
            },
            headers={
                "Authorization": f"Bearer {PARTNER_KEY}",
                "Idempotency-Key": f"current-recommend-{uuid4()}",
            },
        )

    assert response.status_code == 200
    assert response.json()["catalogSnapshotIds"]
    ranked_refs = [item["productRef"] for item in response.json()["recommendations"]]
    assert candidates[0].product_ref in ranked_refs
    assert candidates[1].product_ref in ranked_refs
    assert ranked_refs.index(candidates[0].product_ref) < ranked_refs.index(
        candidates[1].product_ref
    )


def test_simulated_loan_rejection_and_disbursement_are_atomic_and_reproducible(
    database_url: str,
) -> None:
    product_ref = f"hana:loan-{uuid4()}"
    product_snapshot = product(
        product_ref,
        facts={
            "amountMinimumWon": 10_000,
            "amountMaximumWon": 500_000,
            "termMinimumMonths": 6,
            "termMaximumMonths": 36,
            "rateMinimumPercent": 4.2,
        },
        institution_name=f"Hana Loan API {uuid4()}",
    )
    with app_client(database_url) as client:
        customer_id, account_id = seed_account(client, f"loan-flow-{uuid4()}")
        refresh_catalog(
            client.app.state.database,
            [FixtureCatalogSource([product_snapshot])],
            now=NOW,
            lease_owner=f"loan-products-{uuid4()}",
        )
        with client.app.state.database.engine.connect() as connection:
            snapshot_id = connection.execute(
                text(
                    "SELECT snapshot_id FROM loan_product_snapshots "
                    "WHERE product_ref = :product_ref ORDER BY created_at DESC LIMIT 1"
                ),
                {"product_ref": product_ref},
            ).scalar_one()
        base_request = {
            "customerId": customer_id,
            "accountId": account_id,
            "snapshotId": snapshot_id,
            "amountWon": 150_000,
            "termMonths": 12,
        }
        headers = {"Authorization": f"Bearer {PARTNER_KEY}"}
        disbursed_key = f"loan-disbursed-{uuid4()}"
        initial_balance = client.get(f"/v1/accounts/{account_id}", headers=headers).json()[
            "balanceWon"
        ]
        disbursed = client.post(
            "/v1/loans",
            json={**base_request, "scenarioSeed": 0},
            headers={**headers, "Idempotency-Key": disbursed_key},
        )
        rejected = client.post(
            "/v1/loans",
            json={**base_request, "scenarioSeed": 1},
            headers={**headers, "Idempotency-Key": f"loan-rejected-{uuid4()}"},
        )
        outside_published_bound = client.post(
            "/v1/loans",
            json={**base_request, "amountWon": 600_000, "scenarioSeed": 0},
            headers={
                **headers,
                "Idempotency-Key": f"loan-bound-rejected-{uuid4()}",
            },
        )
        replay = client.post(
            "/v1/loans",
            json={**base_request, "scenarioSeed": 0},
            headers={**headers, "Idempotency-Key": disbursed_key},
        )
        account = client.get(f"/v1/accounts/{account_id}", headers=headers)
        disbursed_events = client.get(
            "/v1/events",
            params={"correlationId": disbursed.json()["correlationId"]},
            headers=headers,
        ).json()["items"]
        rejected_events = client.get(
            "/v1/events",
            params={"correlationId": rejected.json()["correlationId"]},
            headers=headers,
        ).json()["items"]
        bound_rejection_events = client.get(
            "/v1/events",
            params={"correlationId": outside_published_bound.json()["correlationId"]},
            headers=headers,
        ).json()["items"]

        with client.app.state.database.engine.connect() as connection:
            loan_statuses = {
                row["loan_id"]: row["status"]
                for row in connection.execute(
                    text(
                        "SELECT loan_id, status FROM loans WHERE loan_id IN "
                        "(:disbursed_id, :rejected_id, :bound_rejected_id)"
                    ),
                    {
                        "disbursed_id": disbursed.json()["loanId"],
                        "rejected_id": rejected.json()["loanId"],
                        "bound_rejected_id": outside_published_bound.json()["loanId"],
                    },
                ).mappings()
            }
            outbox_counts = {
                event["eventId"]: connection.execute(
                    text("SELECT COUNT(*) FROM telemetry_outbox WHERE event_id = :event_id"),
                    {"event_id": event["eventId"]},
                ).scalar_one()
                for event in disbursed_events + rejected_events + bound_rejection_events
            }

    assert (
        disbursed.status_code
        == rejected.status_code
        == outside_published_bound.status_code
        == replay.status_code
        == 200
    )
    assert disbursed.json()["status"] == "disbursed"
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["reason"] == "scenario_seed_rejected"
    assert outside_published_bound.json()["reason"] == "above_published_amount_maximum"
    assert replay.json() == disbursed.json()
    assert account.json()["balanceWon"] == initial_balance + 150_000
    assert loan_statuses == {
        disbursed.json()["loanId"]: "disbursed",
        rejected.json()["loanId"]: "rejected",
        outside_published_bound.json()["loanId"]: "rejected",
    }
    assert [event["eventType"] for event in disbursed_events] == [
        "loan.application.created",
        "account.credited",
        "loan.disbursement.completed",
    ]
    assert [event["eventType"] for event in rejected_events] == [
        "loan.application.created",
        "loan.application.rejected",
    ]
    assert [event["eventType"] for event in bound_rejection_events] == [
        "loan.application.created",
        "loan.application.rejected",
    ]
    assert all(count == 1 for count in outbox_counts.values())
    assert disbursed.json()["eventIds"] == [event["eventId"] for event in disbursed_events]
    assert rejected.json()["eventIds"] == [event["eventId"] for event in rejected_events]
