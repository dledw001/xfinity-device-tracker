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
    upsert_device(
        conn, mac="AA:BB", seen_at="2026-03-02T00:00:00+00:00", host_name="Laptop"
    )
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
    assert payload["devices"][0]["display_name"] == "Laptop"
    assert payload["devices"][0]["is_hidden"] is False
    assert payload["devices"][0]["is_tracked"] is True


def test_devices_latest_with_fresh_db_returns_503_not_500(tmp_path, monkeypatch):
    api = load_api_module(monkeypatch, tmp_path / "fresh.db")

    with pytest.raises(HTTPException) as exc:
        api.devices_latest(x_token="token123")
    assert exc.value.status_code == 503


def test_health_reports_not_ok_when_last_error_present(tmp_path, monkeypatch):
    api = load_api_module(monkeypatch, tmp_path / "router.db")
    api.STATE["last_error"] = "boom"
    api.STATE["last_error_at"] = "2026-03-02T23:30:00+00:00"
    api.STATE["consecutive_failures"] = 2

    payload = api.health()
    assert payload["ok"] is False
    assert payload["last_error"] == "boom"
    assert payload["last_error_at"] == "2026-03-02T23:30:00+00:00"
    assert payload["consecutive_failures"] == 2


def test_devices_alias_endpoint_matches_latest(tmp_path, monkeypatch):
    db_path = tmp_path / "router.db"
    api = load_api_module(monkeypatch, db_path)

    conn = connect(db_path)
    init_db(conn)
    upsert_device(
        conn, mac="AA:BB", seen_at="2026-03-02T00:00:00+00:00", host_name="Laptop"
    )
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

    latest = api.devices_latest(x_token="token123")
    listing = api.devices_list(x_token="token123")
    assert listing == latest


def test_update_device_patch_updates_metadata(tmp_path, monkeypatch):
    db_path = tmp_path / "router.db"
    api = load_api_module(monkeypatch, db_path)

    conn = connect(db_path)
    init_db(conn)
    upsert_device(
        conn, mac="AA:BB", seen_at="2026-03-02T00:00:00+00:00", host_name="wlan0"
    )
    insert_observations(
        conn,
        [
            {
                "mac": "AA:BB",
                "seen_at": "2026-03-02T00:00:00+00:00",
                "status": "online",
                "host_name": "wlan0",
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

    patched = api.update_device(
        "aa:bb",
        api.DevicePatchRequest(
            friendly_name="Dreo Fan",
            category="fan",
            notes="Living room",
            is_hidden=True,
            is_tracked=True,
        ),
        x_token="token123",
    )
    assert patched["mac"] == "AA:BB"
    assert patched["friendly_name"] == "Dreo Fan"
    assert patched["category"] == "fan"
    assert patched["notes"] == "Living room"
    assert patched["is_hidden"] is True
    assert patched["is_tracked"] is True
    assert patched["display_name"] == "Dreo Fan"

    latest = api.devices_latest(x_token="token123")
    device = latest["devices"][0]
    assert device["friendly_name"] == "Dreo Fan"
    assert device["display_name"] == "Dreo Fan"


def test_update_device_patch_rejects_empty_payload(tmp_path, monkeypatch):
    db_path = tmp_path / "router.db"
    api = load_api_module(monkeypatch, db_path)

    conn = connect(db_path)
    init_db(conn)
    upsert_device(
        conn, mac="AA:BB", seen_at="2026-03-02T00:00:00+00:00", host_name="wlan0"
    )
    conn.commit()
    conn.close()

    with pytest.raises(HTTPException) as exc:
        api.update_device("AA:BB", api.DevicePatchRequest(), x_token="token123")
    assert exc.value.status_code == 400
