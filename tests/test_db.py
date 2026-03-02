from db import connect, init_db, insert_observations, upsert_device


def test_init_db_creates_tables(tmp_path):
    db_path = tmp_path / "router.db"
    conn = connect(db_path)
    init_db(conn)

    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('devices','observations')"
    ).fetchall()
    conn.close()

    table_names = sorted([r["name"] for r in rows])
    assert table_names == ["devices", "observations"]


def test_upsert_device_inserts_then_updates(tmp_path):
    db_path = tmp_path / "router.db"
    conn = connect(db_path)
    init_db(conn)

    upsert_device(
        conn, mac="AA:BB", seen_at="2026-03-02T00:00:00+00:00", host_name="Laptop"
    )
    upsert_device(conn, mac="AA:BB", seen_at="2026-03-02T00:05:00+00:00", host_name="")
    conn.commit()

    row = conn.execute("SELECT * FROM devices WHERE mac='AA:BB'").fetchone()
    conn.close()

    assert row["first_seen"] == "2026-03-02T00:00:00+00:00"
    assert row["last_seen"] == "2026-03-02T00:05:00+00:00"
    assert row["last_host_name"] == "Laptop"


def test_insert_observations_persists_rows(tmp_path):
    db_path = tmp_path / "router.db"
    conn = connect(db_path)
    init_db(conn)
    upsert_device(
        conn, mac="AA:BB", seen_at="2026-03-02T00:00:00+00:00", host_name="Laptop"
    )
    rows = [
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
    ]

    insert_observations(conn, rows)
    conn.commit()

    row = conn.execute("SELECT * FROM observations WHERE mac='AA:BB'").fetchone()
    conn.close()

    assert row["status"] == "online"
    assert row["host_name"] == "Laptop"
    assert row["rssi_dbm"] == -55
