"""Bounded HTTP retrieval for explicitly allowlisted public source pages."""

from __future__ import annotations

from collections.abc import Collection
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 10


class SourceUnavailable(RuntimeError):
    """Raised when a public source cannot be read within the adapter policy."""


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        del req, fp, code, msg, headers, newurl
        return None


def fetch_public_html(url: str, *, allowed_urls: Collection[str]) -> str:
    if url not in allowed_urls:
        raise SourceUnavailable("source URL is not allowlisted")
    request = Request(
        url,
        headers={
            "Accept": "text/html",
            "User-Agent": "PodobankBootcampCatalog/0.1 (+synthetic-training-data)",
        },
        method="GET",
    )
    opener = build_opener(_RejectRedirects())
    try:
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise SourceUnavailable("source returned a non-HTML response")
            content_length = response.headers.get("Content-Length")
            if content_length is not None and int(content_length) > MAX_RESPONSE_BYTES:
                raise SourceUnavailable("source response exceeded the size limit")
            body = cast(bytes, response.read(MAX_RESPONSE_BYTES + 1))
    except HTTPError as error:
        raise SourceUnavailable(f"source returned HTTP {error.code}") from None
    except (TimeoutError, URLError, OSError, ValueError) as error:
        del error
        raise SourceUnavailable("source request failed") from None

    if len(body) > MAX_RESPONSE_BYTES:
        raise SourceUnavailable("source response exceeded the size limit")
    try:
        return body.decode("utf-8-sig")
    except UnicodeDecodeError:
        return body.decode("euc-kr", errors="replace")
