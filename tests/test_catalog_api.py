from __future__ import annotations

import importlib.util
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from podobank.catalog import ProductSnapshot
from podobank.catalog_refresh import refresh_catalog
from podobank.db import Database

PARTNER_ID = "shop-simulator"
PARTNER_KEY = "test-partner-secret"


class CatalogSource:
    institution_id = "hana"

    def __init__(self, products: list[ProductSnapshot]) -> None:
        self.products = products
        self.error: Exception | None = None

    def fetch_products(self, retrieved_at: datetime) -> list[ProductSnapshot]:
        if self.error is not None:
            raise self.error
        return [
            replace(product, retrieved_at=retrieved_at, snapshot_id=str(uuid4()))
            for product in self.products
        ]


def make_product(
    product_ref: str, retrieved_at: datetime, institution_name: str = "Hana Bank"
) -> ProductSnapshot:
    return ProductSnapshot(
        product_ref=product_ref,
        institution_name=institution_name,
        product_name=f"Hana API Test Loan {product_ref.rsplit('-', 1)[-1]}",
        product_category="personal_credit",
        facts={"rateMinimumPercent": None, "amountMaximumWon": None},
        source_url="https://www.kebhana.com/cont/mall/mall09/mall0903/mall090303/index.jsp",
        retrieved_at=retrieved_at,
        effective_date=None,
        source_status="active",
    )


def make_client(database_url: str) -> TestClient:
    try:
        module_spec = importlib.util.find_spec("podobank.main")
    except ModuleNotFoundError:
        module_spec = None
    assert module_spec is not None, "The Podobank loan-product API must be implemented."

    from podobank.config import Settings
    from podobank.main import create_app

    settings = Settings(database_url=database_url, partner_keys={PARTNER_ID: PARTNER_KEY})
    return TestClient(create_app(database_url=database_url, settings=settings))


def test_loan_product_api_reads_current_and_historical_snapshots(database_url: str) -> None:
    database = Database(database_url)
    database.initialize_schema()
    product_ref = f"hana:api-{uuid4()}"
    institution_name = f"Hana Bank API {uuid4()}"
    original = make_product(product_ref, datetime(2026, 10, 30, tzinfo=UTC), institution_name)
    revised = replace(
        original,
        facts={"rateMinimumPercent": 4.5, "amountMaximumWon": None},
        retrieved_at=datetime(2026, 10, 31, tzinfo=UTC),
    )
    source = CatalogSource([original])
    try:
        refresh_catalog(
            database,
            [source],
            now=original.retrieved_at,
            lease_owner=f"api-one-{uuid4()}",
        )
        source.products = [revised]
        refresh_catalog(
            database,
            [source],
            now=revised.retrieved_at,
            lease_owner=f"api-two-{uuid4()}",
        )
        source.error = RuntimeError("official source unavailable")
        failed_refresh = refresh_catalog(
            database,
            [source],
            now=datetime(2026, 11, 1, tzinfo=UTC),
            lease_owner=f"api-three-{uuid4()}",
        )
    finally:
        database.dispose()

    with make_client(database_url) as client:
        current = client.get(
            "/v1/loan-products",
            params={"productRef": product_ref},
            headers={"Authorization": f"Bearer {PARTNER_KEY}"},
        )
        history = client.get(
            "/v1/loan-products",
            params={"productRef": product_ref, "includeHistory": "true"},
            headers={"Authorization": f"Bearer {PARTNER_KEY}"},
        )

    assert current.status_code == history.status_code == 200
    assert failed_refresh.source_failures == {"hana": "official source unavailable"}
    assert len(current.json()["items"]) == 1
    assert current.json()["items"][0]["facts"]["rateMinimumPercent"] == 4.5
    assert current.json()["items"][0]["sourceFreshness"] == "stale"
    assert current.json()["items"][0]["factAvailability"]["rateMinimumPercent"] == "published"
    assert current.json()["items"][0]["factAvailability"]["amountMaximumWon"] == "unknown"
    assert len(history.json()["items"]) == 2
    assert [item["facts"]["rateMinimumPercent"] for item in history.json()["items"]] == [
        None,
        4.5,
    ]


def test_product_cursor_excludes_snapshots_added_after_first_page(database_url: str) -> None:
    initial_at = datetime(2026, 10, 29, tzinfo=UTC)
    run_id = uuid4()
    institution_name = f"Hana Bank Cursor {uuid4()}"
    initial_products = [
        make_product(f"hana:cursor-{index}-{run_id}", initial_at, institution_name)
        for index in range(3)
    ]

    with make_client(database_url) as client:
        refresh_catalog(
            client.app.state.database,
            [CatalogSource(initial_products)],
            now=initial_at,
            lease_owner=f"cursor-initial-{uuid4()}",
        )
        first_page = client.get(
            "/v1/loan-products",
            params={
                "institutionName": institution_name,
                "includeHistory": "true",
                "limit": 1,
            },
            headers={"Authorization": f"Bearer {PARTNER_KEY}"},
        ).json()
        later_products = [
            *initial_products,
            make_product(f"hana:cursor-later-{run_id}", initial_at, institution_name),
        ]
        refresh_catalog(
            client.app.state.database,
            [CatalogSource(later_products)],
            now=datetime(2026, 10, 30, tzinfo=UTC),
            lease_owner=f"cursor-later-{uuid4()}",
        )
        items = list(first_page["items"])
        cursor = first_page["nextCursor"]
        while cursor:
            page = client.get(
                "/v1/loan-products",
                params={"cursor": cursor},
                headers={"Authorization": f"Bearer {PARTNER_KEY}"},
            ).json()
            items.extend(page["items"])
            cursor = page["nextCursor"]

    assert len(items) == 3
    assert {item["productRef"] for item in items} == {
        product.product_ref for product in initial_products
    }


def test_loan_product_api_requires_partner_auth_and_rejects_invalid_cursor(
    database_url: str,
) -> None:
    with make_client(database_url) as client:
        unauthenticated = client.get("/v1/loan-products")
        invalid_cursor = client.get(
            "/v1/loan-products",
            params={"cursor": "not-a-cursor"},
            headers={"Authorization": f"Bearer {PARTNER_KEY}"},
        )

    assert unauthenticated.status_code == 401
    assert invalid_cursor.status_code == 400
    assert invalid_cursor.json()["error"]["code"] == "invalid_cursor"
