from __future__ import annotations

import pytest

from podobank.config import Settings


def test_catalog_source_allowlist_and_weekly_interval_are_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PODOBANK_DATABASE_URL", "mysql+pymysql://user:pass@db/podobank")
    monkeypatch.setenv("PODOBANK_PARTNER_KEYS", "{}")
    monkeypatch.setenv("PODOBANK_CATALOG_SOURCE_IDS", "woori")
    monkeypatch.setenv("PODOBANK_CATALOG_REFRESH_INTERVAL_SECONDS", "86400")
    monkeypatch.setenv("PODOBANK_CATALOG_REFRESH_ENABLED", "false")

    settings = Settings.from_environment()

    assert settings.catalog_source_ids == ("woori",)
    assert settings.catalog_refresh_interval_seconds == 86400
    assert settings.catalog_refresh_enabled is False


def test_catalog_source_allowlist_rejects_unknown_and_duplicate_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PODOBANK_DATABASE_URL", "mysql+pymysql://user:pass@db/podobank")
    monkeypatch.setenv("PODOBANK_PARTNER_KEYS", "{}")
    monkeypatch.setenv("PODOBANK_CATALOG_SOURCE_IDS", "hana,unlisted")

    with pytest.raises(ValueError, match="PODOBANK_CATALOG_SOURCE_IDS"):
        Settings.from_environment()
