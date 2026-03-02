import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS devices (
  mac TEXT PRIMARY KEY,
  first_seen TEXT NOT NULL,
  last_seen  TEXT NOT NULL,

  last_host_name TEXT,
  notes TEXT,
  friendly_name TEXT,
  category TEXT,
  is_hidden INTEGER NOT NULL DEFAULT 0,
  is_tracked INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,

  mac TEXT NOT NULL,
  seen_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('online','offline')),

  host_name TEXT,
  dhcp_mode TEXT,
  rssi_dbm INTEGER,
  connection_type TEXT,

  ipv4 TEXT,
  ipv6_global TEXT,
  ipv6_linklocal TEXT,

  source TEXT NOT NULL,

  FOREIGN KEY(mac) REFERENCES devices(mac)
);

CREATE INDEX IF NOT EXISTS idx_obs_mac_seenat ON observations(mac, seen_at);
CREATE INDEX IF NOT EXISTS idx_obs_seenat ON observations(seen_at);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _migrate_devices_table(conn)
    conn.commit()


def _migrate_devices_table(conn: sqlite3.Connection) -> None:
    # Keep existing DBs forward-compatible as the devices schema grows.
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(devices)").fetchall()
    }
    wanted = {
        "friendly_name": "TEXT",
        "category": "TEXT",
        "is_hidden": "INTEGER NOT NULL DEFAULT 0",
        "is_tracked": "INTEGER NOT NULL DEFAULT 1",
    }
    for col, ddl in wanted.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE devices ADD COLUMN {col} {ddl}")


def upsert_device(
    conn: sqlite3.Connection,
    *,
    mac: str,
    seen_at: str,
    host_name: Optional[str],
) -> None:
    conn.execute(
        """
        INSERT INTO devices(mac, first_seen, last_seen, last_host_name)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(mac) DO UPDATE SET
          last_seen = excluded.last_seen,
          last_host_name = COALESCE(NULLIF(excluded.last_host_name, ''), devices.last_host_name)
        """,
        (mac, seen_at, seen_at, host_name),
    )


def insert_observations(conn: sqlite3.Connection, rows: Iterable[Dict[str, Any]]) -> None:
    conn.executemany(
        """
        INSERT INTO observations(
          mac, seen_at, status,
          host_name, dhcp_mode, rssi_dbm, connection_type,
          ipv4, ipv6_global, ipv6_linklocal,
          source
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        [
            (
                r["mac"],
                r["seen_at"],
                r["status"],
                r.get("host_name"),
                r.get("dhcp_mode"),
                r.get("rssi_dbm"),
                r.get("connection_type"),
                r.get("ipv4"),
                r.get("ipv6_global"),
                r.get("ipv6_linklocal"),
                r.get("source", "connected_devices_computers.jst"),
            )
            for r in rows
        ],
    )
