from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event as ThreadEvent
from uuid import uuid4

from podobank.catalog import ProductSnapshot
from podobank.catalog_refresh import RefreshResult, refresh_catalog
from podobank.db import Database
from podobank.source_adapters.hana import HANA_SOURCE_URL, parse_hana_products
from podobank.source_adapters.woori import WOORI_RATE_SOURCE_URL, parse_woori_products

FIXTURES = Path(__file__).parent / "fixtures" / "banks"
RETRIEVED_AT = datetime(2026, 10, 31, 0, 0, tzinfo=UTC)


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def make_product(
    product_ref: str, product_name: str, institution_name: str = "Hana Bank"
) -> ProductSnapshot:
    return ProductSnapshot(
        product_ref=product_ref,
        institution_name=institution_name,
        product_name=product_name,
        product_category="personal_credit",
        facts={"rateMinimumPercent": None, "amountMaximumWon": None},
        source_url=HANA_SOURCE_URL,
        retrieved_at=RETRIEVED_AT,
        effective_date=None,
        source_status="active",
    )


class FixtureSource:
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


def test_hana_parser_reads_only_public_index_and_keeps_unpublished_terms_unknown() -> None:
    products = parse_hana_products(read_fixture("hana.html"), retrieved_at=RETRIEVED_AT)

    assert len(products) == 2
    assert products[0].product_ref == "hana:501_115200"
    assert products[0].product_name == "Hana Starter Credit Loan"
    assert products[0].product_category == "personal_credit"
    assert products[0].source_url == HANA_SOURCE_URL
    assert products[0].retrieved_at == RETRIEVED_AT
    assert products[0].facts["sourcePublishedDate"] == "2026-10-28"
    assert products[0].effective_date is None
    assert products[0].facts["amountMaximumWon"] is None
    assert products[0].facts["rateMinimumPercent"] is None
    assert products[0].facts["rateMaximumPercent"] is None


def test_woori_parser_normalizes_rate_options_and_keeps_missing_fields_unknown() -> None:
    products = parse_woori_products(read_fixture("woori.html"), retrieved_at=RETRIEVED_AT)
    office = next(product for product in products if product.product_ref == "woori:office-loan")
    simple = next(product for product in products if product.product_ref == "woori:simple-loan")

    assert office.product_name == "Woori Office Loan"
    assert office.source_url == WOORI_RATE_SOURCE_URL
    assert office.facts["catalogSourceUrl"].startswith("https://spot.wooribank.com/")
    assert office.retrieved_at == RETRIEVED_AT
    assert office.effective_date.isoformat() == "2026-10-29"
    assert office.facts["amountMaximumWon"] == 200_000_000
    assert office.facts["termMinimumMonths"] == 12
    assert office.facts["termMaximumMonths"] == 60
    assert office.facts["rateMinimumPercent"] == 5.13
    assert office.facts["rateMaximumPercent"] is None
    assert len(office.facts["rateOptions"]) == 2
    assert simple.facts["amountMaximumWon"] is None
    assert simple.facts["termMaximumMonths"] is None
    assert simple.facts["rateOptions"] == []


def test_refresh_versions_products_retires_missing_items_and_preserves_snapshots_on_failure(
    database_url: str,
) -> None:
    first_at = datetime(2026, 10, 28, 0, 0, tzinfo=UTC)
    database = Database(database_url)
    database.initialize_schema()
    institution_name = f"Hana Bank Refresh {uuid4()}"
    first_ref = f"hana:refresh-one-{uuid4()}"
    second_ref = f"hana:refresh-two-{uuid4()}"
    first_product = make_product(first_ref, "Hana Refresh One", institution_name)
    second_product = make_product(second_ref, "Hana Refresh Two", institution_name)
    source = FixtureSource([first_product, second_product])
    try:
        first_refresh = refresh_catalog(database, [source], now=first_at, lease_owner="test-runner")
        source.products = [first_product]
        second_refresh = refresh_catalog(
            database,
            [source],
            now=first_at + timedelta(days=1),
            lease_owner="test-runner-2",
        )
        source.products = []
        empty_refresh = refresh_catalog(
            database,
            [source],
            now=first_at + timedelta(days=2),
            lease_owner="test-runner-empty",
        )
        with database.engine.connect() as connection:
            before_failure = database.catalog_snapshots.list_for_product(connection, first_ref)
        source.error = RuntimeError("source unavailable")
        failed_refresh = refresh_catalog(
            database,
            [source],
            now=first_at + timedelta(days=3),
            lease_owner="test-runner-3",
        )
        with database.engine.connect() as connection:
            after_failure = database.catalog_snapshots.list_for_product(connection, first_ref)
            retired_history = database.catalog_snapshots.list_for_product(connection, second_ref)
    finally:
        database.dispose()

    assert first_refresh.snapshots_saved == 2
    assert second_refresh.retired_products == 1
    assert empty_refresh.source_failures == {"hana": "source returned no loan products"}
    assert [item["source_status"] for item in retired_history] == ["active", "retired"]
    assert failed_refresh.source_failures == {"hana": "source unavailable"}
    assert [item["snapshot_id"] for item in after_failure] == [
        item["snapshot_id"] for item in before_failure
    ]


def test_refresh_lease_skips_a_second_replica_while_source_fetch_is_in_progress(
    database_url: str,
) -> None:
    started = ThreadEvent()
    release = ThreadEvent()

    class BlockingSource(FixtureSource):
        def fetch_products(self, retrieved_at: datetime) -> list[ProductSnapshot]:
            started.set()
            assert release.wait(timeout=5)
            return super().fetch_products(retrieved_at)

    database_one = Database(database_url)
    database_one.initialize_schema()
    database_two = Database(database_url)
    source = BlockingSource(
        [
            make_product(
                f"hana:lease-{uuid4()}",
                "Hana Lease Product",
                f"Hana Bank Lease {uuid4()}",
            )
        ]
    )
    first_result: list[RefreshResult] = []

    def run_first() -> None:
        first_result.append(
            refresh_catalog(
                database_one,
                [source],
                now=RETRIEVED_AT,
                lease_owner="replica-one",
            )
        )

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_first)
            assert started.wait(timeout=5)
            second = refresh_catalog(
                database_two,
                [source],
                now=RETRIEVED_AT,
                lease_owner="replica-two",
            )
            release.set()
            future.result(timeout=5)
    finally:
        release.set()
        database_one.dispose()
        database_two.dispose()

    assert first_result[0].snapshots_saved == 1
    assert second.skipped_in_progress == 1
