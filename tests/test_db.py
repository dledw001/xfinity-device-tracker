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


def test_init_db_migrates_legacy_devices_table(tmp_path):
    db_path = tmp_path / "router.db"
    conn = connect(db_path)
    conn.executescript("""
        CREATE TABLE devices (
          mac TEXT PRIMARY KEY,
          first_seen TEXT NOT NULL,
          last_seen TEXT NOT NULL,
          last_host_name TEXT,
          notes TEXT
        );
        """)
    conn.execute("""
        INSERT INTO devices(mac, first_seen, last_seen, last_host_name, notes)
        VALUES('AA:BB', '2026-03-02T00:00:00+00:00', '2026-03-02T00:00:00+00:00', 'wlan0', 'legacy')
        """)
    conn.commit()

    init_db(conn)

    columns = {
        r["name"]: r for r in conn.execute("PRAGMA table_info(devices)").fetchall()
    }
    row = conn.execute("SELECT * FROM devices WHERE mac='AA:BB'").fetchone()
    conn.close()

    assert "friendly_name" in columns
    assert "category" in columns
    assert "is_hidden" in columns
    assert "is_tracked" in columns
    assert row["notes"] == "legacy"
    assert row["friendly_name"] is None
    assert row["category"] is None
    assert row["is_hidden"] == 0
    assert row["is_tracked"] == 1
