import pytest

from config import env_int, get_settings, require_env


def test_require_env_returns_value(monkeypatch):
    monkeypatch.setenv("ROUTER_IP", "10.0.0.1")
    assert require_env("ROUTER_IP") == "10.0.0.1"


def test_require_env_raises_when_missing(monkeypatch):
    monkeypatch.delenv("ROUTER_IP", raising=False)
    with pytest.raises(RuntimeError, match="Missing required env var: ROUTER_IP"):
        require_env("ROUTER_IP")


def test_env_int_uses_default_on_blank(monkeypatch):
    monkeypatch.setenv("POLL_SECONDS", "")
    assert env_int("POLL_SECONDS", 60) == 60


def test_env_int_raises_on_invalid(monkeypatch):
    monkeypatch.setenv("POLL_SECONDS", "not-an-int")
    with pytest.raises(RuntimeError, match="must be an int"):
        env_int("POLL_SECONDS", 60)


def test_get_settings_and_base_url(monkeypatch):
    monkeypatch.setenv("ROUTER_IP", "192.168.1.1")
    monkeypatch.setenv("ROUTER_USERNAME", "admin")
    monkeypatch.setenv("ROUTER_PASSWORD", "secret")
    monkeypatch.setenv("DB_PATH", "tmp.db")
    monkeypatch.setenv("POLL_SECONDS", "30")
    monkeypatch.setenv("API_TOKEN", "token123")

    settings = get_settings()

    assert settings.router_ip == "192.168.1.1"
    assert settings.router_username == "admin"
    assert settings.router_password == "secret"
    assert settings.db_path == "tmp.db"
    assert settings.poll_seconds == 30
    assert settings.api_token == "token123"
    assert settings.base_url == "https://192.168.1.1"
