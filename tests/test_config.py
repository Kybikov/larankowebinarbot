import os

import pytest

from app.config import Settings


def test_settings_parse_admin_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("ADMIN_IDS", "747629442, 1679569357")
    monkeypatch.setenv("POCKETBASE_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("POCKETBASE_ADMIN_PASSWORD", "secret")

    settings = Settings.from_env()

    assert settings.admin_ids == (747629442, 1679569357)
    assert settings.timezone == "Europe/Kyiv"
    assert settings.meta_pixel_id == ""
    assert settings.attribution_port == 8080


def test_settings_require_admins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("ADMIN_IDS", "")
    monkeypatch.setenv("POCKETBASE_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("POCKETBASE_ADMIN_PASSWORD", "secret")

    with pytest.raises(RuntimeError):
        Settings.from_env()
