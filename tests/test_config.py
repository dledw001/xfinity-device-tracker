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
    monkeypatch.setenv("POLL_BACKOFF_MAX_SECONDS", "180")
    monkeypatch.setenv("API_TOKEN", "token123")
    monkeypatch.setenv("ROUTER_CONNECT_TIMEOUT_SECONDS", "4")
    monkeypatch.setenv("ROUTER_READ_TIMEOUT_SECONDS", "25")
    monkeypatch.setenv("ROUTER_FETCH_RETRIES", "3")
    monkeypatch.setenv("ROUTER_RETRY_BACKOFF_SECONDS", "2")

    settings = get_settings()

    assert settings.router_ip == "192.168.1.1"
    assert settings.router_username == "admin"
    assert settings.router_password == "secret"
    assert settings.db_path == "tmp.db"
    assert settings.poll_seconds == 30
    assert settings.poll_backoff_max_seconds == 180
    assert settings.api_token == "token123"
    assert settings.router_connect_timeout_seconds == 4
    assert settings.router_read_timeout_seconds == 25
    assert settings.router_fetch_retries == 3
    assert settings.router_retry_backoff_seconds == 2
    assert settings.base_url == "https://192.168.1.1"
