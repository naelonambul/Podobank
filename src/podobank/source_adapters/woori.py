"""Adapter for Woori Bank's public loan catalog and rate disclosure."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup, Tag

from podobank.catalog import ProductSnapshot
from podobank.source_adapters._http import fetch_public_html

WOORI_CATALOG_SOURCE_URL = "https://spot.wooribank.com/pot/Dream?withyou=POLON0102"
WOORI_RATE_SOURCE_URL = (
    "https://spot.wooribank.com/pot/jcc?PRD_CLF_DSCD=01&__ID=c012664&withyou=CQPNC0033"
)


class WooriCatalogSource:
    institution_id = "woori"

    def fetch_products(self, retrieved_at: datetime) -> list[ProductSnapshot]:
        return fetch_woori_products(retrieved_at)


def fetch_woori_products(retrieved_at: datetime) -> list[ProductSnapshot]:
    allowed_urls = {WOORI_CATALOG_SOURCE_URL, WOORI_RATE_SOURCE_URL}
    catalog_html = fetch_public_html(WOORI_CATALOG_SOURCE_URL, allowed_urls=allowed_urls)
    rate_html = fetch_public_html(WOORI_RATE_SOURCE_URL, allowed_urls=allowed_urls)
    return parse_woori_products(catalog_html, rate_html, retrieved_at=retrieved_at)


def parse_woori_products(
    catalog_html: str,
    rate_html: str | None = None,
    *,
    retrieved_at: datetime,
) -> list[ProductSnapshot]:
    catalog_soup = BeautifulSoup(catalog_html, "html.parser")
    rate_soup = BeautifulSoup(rate_html if rate_html is not None else catalog_html, "html.parser")
    products: list[ProductSnapshot] = []
    for item in catalog_soup.select("ul.new-main-list li"):
        title = item.select_one("dt a, dt, a")
        if title is None:
            continue
        product_name = title.get_text(" ", strip=True)
        if not product_name:
            continue
        product_ref = _product_reference(item, product_name)
        item_text = item.get_text(" ", strip=True)
        amount_maximum = _amount_maximum(item_text)
        term_minimum, term_maximum = _term_bounds(item_text)
        options, rate_minimum = _rate_options(rate_soup, product_name)
        effective_date = _effective_date(rate_soup)
        products.append(
            ProductSnapshot(
                product_ref=f"woori:{product_ref}",
                institution_name="Woori Bank",
                product_name=product_name,
                product_category="personal_credit",
                facts={
                    "amountMaximumWon": amount_maximum,
                    "termMinimumMonths": term_minimum,
                    "termMaximumMonths": term_maximum,
                    "rateMinimumPercent": rate_minimum,
                    "rateMaximumPercent": None,
                    "rateOptions": options,
                    "catalogSourceUrl": WOORI_CATALOG_SOURCE_URL,
                },
                source_url=WOORI_RATE_SOURCE_URL,
                retrieved_at=retrieved_at,
                effective_date=effective_date,
            )
        )
    if not products:
        raise ValueError("Woori loan catalog markup was not recognized")
    return products


def _product_reference(item: Tag, product_name: str) -> str:
    for key in ("data-product-ref", "data-prd-code", "data-prd-cd", "data-product-code"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return _safe_ref(value)
    link = item.select_one("a[href]")
    if link is not None:
        query = parse_qs(urlsplit(str(link.get("href", ""))).query)
        for key in ("PRD_CD", "prdCd", "productCode", "prodCd"):
            values = query.get(key)
            if values and values[0].strip():
                return _safe_ref(values[0])
    return _safe_ref(product_name)


def _safe_ref(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    slug = re.sub(r"[^\w-]+", "-", normalized, flags=re.UNICODE).strip("-")
    if not slug:
        raise ValueError("Woori product reference was empty")
    return slug[:140]


def _amount_maximum(value: str) -> int | None:
    normalized = value.replace(",", "").replace(" ", "")
    patterns = (
        (
            r"(?:최대|한도|maximum|max(?:imumamount)?(?:krw)?)[:：]?"
            r"([0-9]+(?:\.[0-9]+)?)억원?",
            100_000_000,
        ),
        (
            r"(?:최대|한도|maximum|max(?:imumamount)?(?:krw)?)[:：]?"
            r"([0-9]+(?:\.[0-9]+)?)천만원",
            10_000_000,
        ),
        (
            r"(?:최대|한도|maximum|max(?:imumamount)?(?:krw)?)[:：]?"
            r"([0-9]+(?:\.[0-9]+)?)백만원",
            1_000_000,
        ),
        (
            r"(?:최대|한도|maximum|max(?:imumamount)?(?:krw)?)[:：]?₩?([0-9]+)원?",
            1,
        ),
    )
    for pattern, multiplier in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match is not None:
            return int(float(match.group(1)) * multiplier)
    return None


def _term_bounds(value: str) -> tuple[int | None, int | None]:
    normalized = value.lower().replace(" ", "")
    month_range = re.search(
        r"(\d{1,3})(?:개월|months?)?(?:이상|부터|to|~|-)(\d{1,3})(?:개월|months?)",
        normalized,
    )
    if month_range is not None:
        return int(month_range.group(1)), int(month_range.group(2))
    year_range = re.search(
        r"(\d{1,2})(?:년|years?)?(?:이상|부터|to|~|-)(\d{1,2})(?:년|years?)",
        normalized,
    )
    if year_range is not None:
        return int(year_range.group(1)) * 12, int(year_range.group(2)) * 12
    maximum = re.search(r"(?:최장|최대|upto)(\d{1,3})(?:개월|months?)", normalized)
    if maximum is not None:
        return None, int(maximum.group(1))
    return None, None


def _rate_options(
    soup: BeautifulSoup, product_name: str
) -> tuple[list[dict[str, object]], float | None]:
    options: list[dict[str, object]] = []
    for heading in soup.select("h3.fleft"):
        if _normalize_text(heading.get_text(" ", strip=True)) != _normalize_text(product_name):
            continue
        table = heading.find_next("table", class_="tbl-type-1")
        if table is None:
            continue
        headers = [cell.get_text(" ", strip=True) for cell in table.select("thead th")]
        for row in table.select("tbody tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all("td")]
            if not cells:
                continue
            values_by_header = {
                headers[index]: cells[index] for index in range(min(len(headers), len(cells)))
            }
            numbers = [_parse_rate(cell) for cell in cells[1:]]
            base_rate = _rate_for_header(values_by_header, ("base rate", "기준금리"))
            discount_rate = _rate_for_header(values_by_header, ("discount", "우대금리"))
            lowest_rate = _rate_for_header(values_by_header, ("lowest published rate", "최저금리"))
            if lowest_rate is None and numbers:
                lowest_rate = numbers[-1]
            options.append(
                {
                    "rateType": cells[0],
                    "baseRatePercent": base_rate,
                    "discountPercent": discount_rate,
                    "lowestPublishedRatePercent": lowest_rate,
                }
            )
    published_rates = [
        option["lowestPublishedRatePercent"]
        for option in options
        if isinstance(option["lowestPublishedRatePercent"], (int, float))
    ]
    return options, min(published_rates) if published_rates else None


def _rate_for_header(values: dict[str, str], fragments: tuple[str, ...]) -> float | None:
    for header, value in values.items():
        if any(fragment.lower() in header.lower() for fragment in fragments):
            return _parse_rate(value)
    return None


def _parse_rate(value: str) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", value.replace(",", ""))
    return float(match.group()) if match is not None else None


def _effective_date(soup: BeautifulSoup) -> date | None:
    date_node = soup.select_one(".rate-reference-date")
    value = (
        date_node.get_text(" ", strip=True)
        if date_node is not None
        else soup.get_text(" ", strip=True)
    )
    match = re.search(
        r"(?:rate reference date|effective date|금리(?:적용)?기준일|기준일)"
        r"[^0-9]{0,32}(20\d{2})[./-](\d{1,2})[./-](\d{1,2})",
        value,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()
