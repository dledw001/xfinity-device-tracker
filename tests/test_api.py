import importlib
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from db import connect, init_db, insert_observations, upsert_device


def load_api_module(monkeypatch, db_path, extra_env=None):
    monkeypatch.setenv("ROUTER_IP", "10.0.0.1")
    monkeypatch.setenv("ROUTER_USERNAME", "admin")
    monkeypatch.setenv("ROUTER_PASSWORD", "password")
    monkeypatch.setenv("API_TOKEN", "token123")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("POLL_SECONDS", "60")
    monkeypatch.setenv("POLL_BACKOFF_MAX_SECONDS", "300")
    monkeypatch.setenv("ROUTER_CONNECT_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("ROUTER_READ_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("ROUTER_FETCH_RETRIES", "2")
    monkeypatch.setenv("ROUTER_RETRY_BACKOFF_SECONDS", "1")
    if extra_env:
        for key, value in extra_env.items():
            monkeypatch.setenv(key, str(value))

    if "api" in sys.modules:
        del sys.modules["api"]
    return importlib.import_module("api")


def test_require_token_rejects_invalid_token(tmp_path, monkeypatch):
    api = load_api_module(monkeypatch, tmp_path / "router.db")

    with pytest.raises(HTTPException) as exc:
        api.require_token("wrong")
    assert exc.value.status_code == 401


def test_protected_endpoints_require_token(tmp_path, monkeypatch):
    api = load_api_module(monkeypatch, tmp_path / "router.db")

    with pytest.raises(HTTPException) as latest_exc:
        api.devices_latest(x_token=None)
    assert latest_exc.value.status_code == 401

    with pytest.raises(HTTPException) as list_exc:
        api.devices_list(x_token="bad")
    assert list_exc.value.status_code == 401


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
    assert payload["devices"][0]["groups"] == []


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


def test_favicon_route_returns_file_response(tmp_path, monkeypatch):
    api = load_api_module(monkeypatch, tmp_path / "router.db")

    response = api.favicon()
    assert isinstance(response, FileResponse)
    assert Path(response.path).name == "favicon.ico"


def test_favicon_route_404_when_file_missing(tmp_path, monkeypatch):
    api = load_api_module(monkeypatch, tmp_path / "router.db")
    monkeypatch.setattr(api, "FAVICON_PATH", tmp_path / "does-not-exist.ico")

    with pytest.raises(HTTPException) as exc:
        api.favicon()
    assert exc.value.status_code == 404


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


def test_groups_endpoints_require_token(tmp_path, monkeypatch):
    api = load_api_module(monkeypatch, tmp_path / "router.db")

    with pytest.raises(HTTPException) as exc:
        api.groups_list(x_token=None)
    assert exc.value.status_code == 401


def test_groups_create_and_list(tmp_path, monkeypatch):
    api = load_api_module(monkeypatch, tmp_path / "router.db")

    created = api.groups_create(
        api.GroupCreateRequest(name="Living Room"),
        x_token="token123",
    )
    assert created["id"] > 0
    assert created["name"] == "Living Room"

    listed = api.groups_list(x_token="token123")
    assert listed["count"] == 1
    assert listed["groups"][0]["name"] == "Living Room"
    assert listed["groups"][0]["device_count"] == 0


def test_groups_create_rejects_duplicate_name(tmp_path, monkeypatch):
    api = load_api_module(monkeypatch, tmp_path / "router.db")
    api.groups_create(api.GroupCreateRequest(name="IoT"), x_token="token123")

    with pytest.raises(HTTPException) as exc:
        api.groups_create(api.GroupCreateRequest(name="IoT"), x_token="token123")
    assert exc.value.status_code == 409


def test_device_group_assignment_and_filtering(tmp_path, monkeypatch):
    db_path = tmp_path / "router.db"
    api = load_api_module(monkeypatch, db_path)

    conn = connect(db_path)
    init_db(conn)
    upsert_device(
        conn, mac="AA:BB", seen_at="2026-03-02T00:00:00+00:00", host_name="Laptop"
    )
    upsert_device(
        conn, mac="CC:DD", seen_at="2026-03-02T00:00:00+00:00", host_name="Phone"
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
            },
            {
                "mac": "CC:DD",
                "seen_at": "2026-03-02T00:00:00+00:00",
                "status": "offline",
                "host_name": "Phone",
                "dhcp_mode": "DHCP",
                "rssi_dbm": None,
                "connection_type": "WiFi",
                "ipv4": "10.0.0.3",
                "ipv6_global": None,
                "ipv6_linklocal": None,
                "source": "connected_devices_computers.jst",
            },
        ],
    )
    conn.commit()
    conn.close()

    group = api.groups_create(api.GroupCreateRequest(name="Family"), x_token="token123")
    api.add_device_group("aa:bb", group["id"], x_token="token123")

    all_devices = api.devices_list(x_token="token123")
    by_mac = {d["mac"]: d for d in all_devices["devices"]}
    assert by_mac["AA:BB"]["groups"] == ["Family"]
    assert by_mac["CC:DD"]["groups"] == []

    filtered = api.devices_list(x_token="token123", group_id=group["id"])
    assert filtered["count"] == 1
    assert filtered["devices"][0]["mac"] == "AA:BB"

    api.remove_device_group("AA:BB", group["id"], x_token="token123")
    filtered_after = api.devices_list(x_token="token123", group_id=group["id"])
    assert filtered_after["count"] == 0


def test_devices_filter_unknown_group_returns_404(tmp_path, monkeypatch):
    api = load_api_module(monkeypatch, tmp_path / "router.db")

    with pytest.raises(HTTPException) as exc:
        api.devices_list(x_token="token123", group_id=9999)
    assert exc.value.status_code == 404


def test_bulk_group_assign_tags_multiple_devices(tmp_path, monkeypatch):
    db_path = tmp_path / "router.db"
    api = load_api_module(monkeypatch, db_path)

    conn = connect(db_path)
    init_db(conn)
    upsert_device(
        conn, mac="AA:BB", seen_at="2026-03-02T00:00:00+00:00", host_name="Laptop"
    )
    upsert_device(
        conn, mac="CC:DD", seen_at="2026-03-02T00:00:00+00:00", host_name="Phone"
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
            },
            {
                "mac": "CC:DD",
                "seen_at": "2026-03-02T00:00:00+00:00",
                "status": "online",
                "host_name": "Phone",
                "dhcp_mode": "DHCP",
                "rssi_dbm": -45,
                "connection_type": "WiFi",
                "ipv4": "10.0.0.3",
                "ipv6_global": None,
                "ipv6_linklocal": None,
                "source": "connected_devices_computers.jst",
            },
        ],
    )
    conn.commit()
    conn.close()

    group = api.groups_create(api.GroupCreateRequest(name="BulkTag"), x_token="token123")
    api.bulk_assign_group(
        group["id"],
        api.BulkGroupAssignRequest(macs=["aa:bb", "CC:DD"]),
        x_token="token123",
    )

    filtered = api.devices_list(x_token="token123", group_id=group["id"])
    assert filtered["count"] == 2


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


def test_update_device_patch_404_for_unknown_device(tmp_path, monkeypatch):
    db_path = tmp_path / "router.db"
    api = load_api_module(monkeypatch, db_path)

    with pytest.raises(HTTPException) as exc:
        api.update_device(
            "AA:BB",
            api.DevicePatchRequest(friendly_name="Unknown"),
            x_token="token123",
        )
    assert exc.value.status_code == 404


def test_update_device_patch_allows_clearing_nullable_string_fields(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "router.db"
    api = load_api_module(monkeypatch, db_path)

    conn = connect(db_path)
    init_db(conn)
    upsert_device(
        conn, mac="AA:BB", seen_at="2026-03-02T00:00:00+00:00", host_name="wlan0"
    )
    conn.commit()
    conn.close()

    api.update_device(
        "AA:BB",
        api.DevicePatchRequest(
            friendly_name="Office TV", category="tv", notes="Legacy note"
        ),
        x_token="token123",
    )
    patched = api.update_device(
        "AA:BB",
        api.DevicePatchRequest(friendly_name=None, category=None, notes=None),
        x_token="token123",
    )

    assert patched["friendly_name"] is None
    assert patched["category"] is None
    assert patched["notes"] is None
    assert patched["display_name"] == "wlan0"


def test_update_device_patch_rejects_null_bool_fields(tmp_path, monkeypatch):
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
        api.update_device(
            "AA:BB",
            api.DevicePatchRequest(is_hidden=None),
            x_token="token123",
        )
    assert exc.value.status_code == 400


def test_poll_loop_sets_success_state(tmp_path, monkeypatch):
    db_path = tmp_path / "router.db"
    api = load_api_module(monkeypatch, db_path)

    class StopAfterOneWait:
        def __init__(self):
            self._done = False
            self.wait_seconds = None

        def is_set(self):
            return self._done

        def wait(self, seconds):
            self.wait_seconds = seconds
            self._done = True

    stop = StopAfterOneWait()
    fake_client = Mock()
    fake_client.fetch_connected_devices_html.return_value = "<html>ok</html>"
    monkeypatch.setattr(api, "RouterClient", lambda *args, **kwargs: fake_client)
    monkeypatch.setattr(
        api,
        "ingest_html_snapshot",
        lambda _db_path, _html: {"seen_at": "2026-03-03T00:00:00+00:00"},
    )
    api.STATE.update(
        {
            "last_ingest": None,
            "last_result": None,
            "last_error": "prev error",
            "last_error_at": "2026-03-02T00:00:00+00:00",
            "consecutive_failures": 7,
        }
    )

    api.poll_loop(stop)

    assert api.STATE["last_ingest"] == "2026-03-03T00:00:00+00:00"
    assert api.STATE["last_error"] is None
    assert api.STATE["last_error_at"] is None
    assert api.STATE["consecutive_failures"] == 0
    assert stop.wait_seconds == 60


def test_poll_loop_sets_failure_state(tmp_path, monkeypatch):
    db_path = tmp_path / "router.db"
    api = load_api_module(monkeypatch, db_path)

    class StopAfterOneWait:
        def __init__(self):
            self._done = False
            self.wait_seconds = None

        def is_set(self):
            return self._done

        def wait(self, seconds):
            self.wait_seconds = seconds
            self._done = True

    stop = StopAfterOneWait()
    fake_client = Mock()
    fake_client.fetch_connected_devices_html.side_effect = TimeoutError("timed out")
    monkeypatch.setattr(api, "RouterClient", lambda *args, **kwargs: fake_client)
    monkeypatch.setattr(api, "now_iso_utc", lambda: "2026-03-03T00:10:00+00:00")
    api.STATE.update(
        {
            "last_ingest": None,
            "last_result": None,
            "last_error": None,
            "last_error_at": None,
            "consecutive_failures": 1,
        }
    )

    api.poll_loop(stop)

    assert "timed out" in api.STATE["last_error"]
    assert api.STATE["last_error_at"] == "2026-03-03T00:10:00+00:00"
    assert api.STATE["consecutive_failures"] == 2
    assert stop.wait_seconds == 120


def test_poll_loop_uses_router_client_timeouts_and_retries(tmp_path, monkeypatch):
    db_path = tmp_path / "router.db"
    api = load_api_module(
        monkeypatch,
        db_path,
        extra_env={
            "ROUTER_CONNECT_TIMEOUT_SECONDS": "4",
            "ROUTER_READ_TIMEOUT_SECONDS": "45",
            "ROUTER_FETCH_RETRIES": "3",
            "ROUTER_RETRY_BACKOFF_SECONDS": "2",
        },
    )

    captured = {}

    class StopAfterOneWait:
        def __init__(self):
            self._done = False

        def is_set(self):
            return self._done

        def wait(self, _seconds):
            self._done = True

    class FakeClient:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

        def fetch_connected_devices_html(self):
            return "<html>ok</html>"

    monkeypatch.setattr(api, "RouterClient", FakeClient)
    monkeypatch.setattr(
        api,
        "ingest_html_snapshot",
        lambda _db_path, _html: {"seen_at": "2026-03-03T00:00:00+00:00"},
    )

    api.poll_loop(StopAfterOneWait())

    assert captured["connect_timeout_seconds"] == 4
    assert captured["read_timeout_seconds"] == 45
    assert captured["fetch_retries"] == 3
    assert captured["retry_backoff_seconds"] == 2
