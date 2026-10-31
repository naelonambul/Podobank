"""Adapter for Hana Bank's public credit-loan disclosure index."""

from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from podobank.catalog import ProductSnapshot
from podobank.source_adapters._http import fetch_public_html

HANA_SOURCE_URL = "https://www.kebhana.com/cont/mall/mall09/mall0903/mall090303/index.jsp"


class HanaCatalogSource:
    institution_id = "hana"

    def fetch_products(self, retrieved_at: datetime) -> list[ProductSnapshot]:
        return fetch_hana_products(retrieved_at)


def fetch_hana_products(retrieved_at: datetime) -> list[ProductSnapshot]:
    html = fetch_public_html(HANA_SOURCE_URL, allowed_urls={HANA_SOURCE_URL})
    return parse_hana_products(html, retrieved_at=retrieved_at)


def parse_hana_products(html: str, *, retrieved_at: datetime) -> list[ProductSnapshot]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.tblBoard")
    if table is None:
        raise ValueError("Hana loan-product index markup was not recognized")

    products: list[ProductSnapshot] = []
    for row in table.select("tbody tr"):
        link = row.select_one("a[href]")
        if link is None:
            continue
        path = urlsplit(str(link.get("href", ""))).path
        match = re.search(r"/([A-Za-z0-9_-]+)\.jsp$", path)
        if match is None:
            continue
        cells = row.find_all("td", recursive=False)
        published_date = (
            _date_from_text(cells[1].get_text(" ", strip=True)) if len(cells) > 1 else None
        )
        facts: dict[str, object] = {
            "sourcePublishedDate": published_date.isoformat() if published_date else None,
            "amountMaximumWon": None,
            "termMinimumMonths": None,
            "termMaximumMonths": None,
            "rateMinimumPercent": None,
            "rateMaximumPercent": None,
            "rateOptions": [],
        }
        products.append(
            ProductSnapshot(
                product_ref=f"hana:{match.group(1)}",
                institution_name="Hana Bank",
                product_name=link.get_text(" ", strip=True),
                product_category="personal_credit",
                facts=facts,
                source_url=HANA_SOURCE_URL,
                retrieved_at=retrieved_at,
                effective_date=None,
            )
        )
    if not products:
        raise ValueError("Hana loan-product index contained no recognizable products")
    return products


def _date_from_text(value: str) -> date | None:
    match = re.search(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", value)
    if match is None:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None
