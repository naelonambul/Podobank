from __future__ import annotations

import pytest

from podobank.source_adapters import _http
from podobank.source_adapters._http import SourceUnavailable, fetch_public_html


def test_public_html_fetch_rejects_urls_outside_the_adapter_allowlist() -> None:
    allowed_urls = {"https://bank.example/public/catalog"}

    with pytest.raises(SourceUnavailable, match="not allowlisted"):
        fetch_public_html("http://127.0.0.1/private", allowed_urls=allowed_urls)


def test_public_html_fetch_rejects_responses_over_the_size_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Headers:
        def get_content_type(self) -> str:
            return "text/html"

        def get(self, name: str) -> str | None:
            del name
            return None

    class Response:
        headers = Headers()

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def read(self, amount: int) -> bytes:
            return b"x" * amount

    class Opener:
        def open(self, request: object, *, timeout: int) -> Response:
            del request, timeout
            return Response()

    monkeypatch.setattr(_http, "MAX_RESPONSE_BYTES", 4)
    monkeypatch.setattr(_http, "build_opener", lambda handler: Opener())

    with pytest.raises(SourceUnavailable, match="size limit"):
        fetch_public_html(
            "https://bank.example/public/catalog",
            allowed_urls={"https://bank.example/public/catalog"},
        )
