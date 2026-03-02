import importlib
import sys

import pytest
from fastapi import HTTPException

from db import connect, init_db, insert_observations, upsert_device


def load_api_module(monkeypatch, db_path):
    monkeypatch.setenv("ROUTER_IP", "10.0.0.1")
    monkeypatch.setenv("ROUTER_USERNAME", "admin")
    monkeypatch.setenv("ROUTER_PASSWORD", "password")
    monkeypatch.setenv("API_TOKEN", "token123")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("POLL_SECONDS", "60")

    if "api" in sys.modules:
        del sys.modules["api"]
    return importlib.import_module("api")


def test_require_token_rejects_invalid_token(tmp_path, monkeypatch):
    api = load_api_module(monkeypatch, tmp_path / "router.db")

    with pytest.raises(HTTPException) as exc:
        api.require_token("wrong")
    assert exc.value.status_code == 401


def test_devices_latest_returns_data_for_latest_snapshot(tmp_path, monkeypatch):
    db_path = tmp_path / "router.db"
    api = load_api_module(monkeypatch, db_path)

    conn = connect(db_path)
    init_db(conn)
    upsert_device(conn, mac="AA:BB", seen_at="2026-03-02T00:00:00+00:00", host_name="Laptop")
    insert_observations(
        conn,
        [
            {
                "mac": "AA:BB",
                "seen_at": "2026-03-02T00:00:00+00:00",
                "status": "online",
                "host_name": "Laptop",
                "dhcp_mode": "DHCP",
                "rssi_dbm": -55,
                "connection_type": "WiFi",
                "ipv4": "10.0.0.2",
                "ipv6_global": None,
                "ipv6_linklocal": None,
                "source": "connected_devices_computers.jst",
            }
        ],
    )
    conn.commit()
    conn.close()

    payload = api.devices_latest(x_token="token123")
    assert payload["seen_at"] == "2026-03-02T00:00:00+00:00"
    assert payload["count"] == 1
    assert payload["devices"][0]["mac"] == "AA:BB"


def test_devices_latest_with_fresh_db_returns_503_not_500(tmp_path, monkeypatch):
    api = load_api_module(monkeypatch, tmp_path / "fresh.db")

    with pytest.raises(HTTPException) as exc:
        api.devices_latest(x_token="token123")
    assert exc.value.status_code == 503


def test_health_reports_not_ok_when_last_error_present(tmp_path, monkeypatch):
    api = load_api_module(monkeypatch, tmp_path / "router.db")
    api.STATE["last_error"] = "boom"

    payload = api.health()
    assert payload["ok"] is False
