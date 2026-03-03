from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import get_settings
from backend import RouterClient
from ingest import ingest_html_snapshot
from db import connect, init_db

STATE: Dict[str, Any] = {
    "last_ingest": None,
    "last_result": None,
    "last_error": None,
    "last_error_at": None,
    "consecutive_failures": 0,
}
settings = get_settings()
FAVICON_PATH = Path(__file__).resolve().parent / "static" / "favicon.ico"


class DevicePatchRequest(BaseModel):
    friendly_name: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    is_hidden: Optional[bool] = None
    is_tracked: Optional[bool] = None
    model_config = {"extra": "forbid"}


class HealthResponse(BaseModel):
    ok: bool
    last_ingest: Optional[str] = None
    last_error: Optional[str] = None
    last_error_at: Optional[str] = None
    consecutive_failures: int
    poll_seconds: int


class DeviceSnapshot(BaseModel):
    mac: str
    status: str
    host_name: Optional[str] = None
    dhcp_mode: Optional[str] = None
    rssi_dbm: Optional[int] = None
    connection_type: Optional[str] = None
    ipv4: Optional[str] = None
    ipv6_global: Optional[str] = None
    ipv6_linklocal: Optional[str] = None
    friendly_name: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    is_hidden: bool
    is_tracked: bool
    last_host_name: Optional[str] = None
    first_seen: str
    last_seen: str
    display_name: str


class DevicesLatestResponse(BaseModel):
    seen_at: str
    count: int
    devices: List[DeviceSnapshot]


class DeviceMetadataResponse(BaseModel):
    mac: str
    first_seen: str
    last_seen: str
    last_host_name: Optional[str] = None
    notes: Optional[str] = None
    friendly_name: Optional[str] = None
    category: Optional[str] = None
    is_hidden: bool
    is_tracked: bool
    display_name: str


def require_token(x_token: Optional[str]) -> None:
    if x_token != settings.api_token:
        raise HTTPException(status_code=401, detail="bad token")


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def poll_loop(stop_event: Event) -> None:
    client = RouterClient(
        settings.base_url, settings.router_username, settings.router_password
    )

    while not stop_event.is_set():
        try:
            html = client.fetch_connected_devices_html()
            result = ingest_html_snapshot(settings.db_path, html)
            STATE["last_ingest"] = result.get("seen_at")
            STATE["last_result"] = result
            STATE["last_error"] = None
            STATE["last_error_at"] = None
            STATE["consecutive_failures"] = 0
        except Exception as e:
            STATE["last_error"] = str(e)
            STATE["last_error_at"] = now_iso_utc()
            STATE["consecutive_failures"] = (
                int(STATE.get("consecutive_failures", 0)) + 1
            )
        stop_event.wait(settings.poll_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = Event()
    t = Thread(target=poll_loop, args=(stop_event,), daemon=True)
    t.start()
    try:
        yield
    finally:
        stop_event.set()
        t.join(timeout=2)


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def normalize_mac(mac: str) -> str:
    return mac.strip().upper()


def to_display_name(device: Dict[str, Any]) -> str:
    return (
        device.get("friendly_name")
        or device.get("host_name")
        or device.get("last_host_name")
        or device["mac"]
    )


def fetch_latest_devices_payload() -> Dict[str, Any]:
    conn = connect(settings.db_path)
    init_db(conn)

    try:
        row = conn.execute(
            "SELECT MAX(seen_at) AS seen_at FROM observations"
        ).fetchone()
        if not row or not row["seen_at"]:
            raise HTTPException(
                status_code=503, detail=STATE["last_error"] or "no data yet"
            )
        seen_at = row["seen_at"]

        devices = conn.execute(
            """
            SELECT
              o.mac, o.status, o.host_name, o.dhcp_mode, o.rssi_dbm, o.connection_type,
              o.ipv4, o.ipv6_global, o.ipv6_linklocal,
              d.friendly_name, d.category, d.notes, d.is_hidden, d.is_tracked,
              d.last_host_name, d.first_seen, d.last_seen
            FROM observations o
            JOIN devices d ON d.mac = o.mac
            WHERE o.seen_at = ?
            ORDER BY o.status DESC, COALESCE(d.friendly_name, o.host_name, o.mac)
            """,
            (seen_at,),
        ).fetchall()
    finally:
        conn.close()

    materialized = [dict(d) for d in devices]
    for device in materialized:
        device["is_hidden"] = bool(device["is_hidden"])
        device["is_tracked"] = bool(device["is_tracked"])
        device["display_name"] = to_display_name(device)

    return {"seen_at": seen_at, "count": len(materialized), "devices": materialized}


@app.get("/health", response_model=HealthResponse)
def health():
    return {
        "ok": STATE["last_error"] is None,
        "last_ingest": STATE["last_ingest"],
        "last_error": STATE["last_error"],
        "last_error_at": STATE["last_error_at"],
        "consecutive_failures": STATE["consecutive_failures"],
        "poll_seconds": settings.poll_seconds,
    }


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    if not FAVICON_PATH.exists():
        raise HTTPException(status_code=404, detail="favicon not found")
    return FileResponse(FAVICON_PATH)


@app.get("/devices/latest", response_model=DevicesLatestResponse)
def devices_latest(x_token: Optional[str] = Header(default=None)):
    require_token(x_token)
    return fetch_latest_devices_payload()


@app.get("/devices", response_model=DevicesLatestResponse)
def devices_list(x_token: Optional[str] = Header(default=None)):
    require_token(x_token)
    return fetch_latest_devices_payload()


@app.patch("/devices/{mac}", response_model=DeviceMetadataResponse)
def update_device(
    mac: str, patch: DevicePatchRequest, x_token: Optional[str] = Header(default=None)
):
    require_token(x_token)

    raw_update_map = patch.model_dump(exclude_unset=True)
    update_map: Dict[str, Any] = {}
    for field, val in raw_update_map.items():
        if field in ("is_hidden", "is_tracked"):
            if val is None:
                raise HTTPException(status_code=400, detail=f"{field} cannot be null")
            update_map[field] = int(bool(val))
        else:
            update_map[field] = val

    if not update_map:
        raise HTTPException(status_code=400, detail="no fields to update")

    mac_norm = normalize_mac(mac)
    conn = connect(settings.db_path)
    init_db(conn)
    try:
        exists = conn.execute(
            "SELECT 1 FROM devices WHERE mac = ?", (mac_norm,)
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="device not found")

        set_sql = ", ".join([f"{k} = ?" for k in update_map])
        params = list(update_map.values()) + [mac_norm]
        conn.execute(f"UPDATE devices SET {set_sql} WHERE mac = ?", params)
        conn.commit()

        row = conn.execute(
            """
            SELECT
              mac, first_seen, last_seen, last_host_name,
              notes, friendly_name, category, is_hidden, is_tracked
            FROM devices
            WHERE mac = ?
            """,
            (mac_norm,),
        ).fetchone()
    finally:
        conn.close()

    payload = dict(row)
    payload["is_hidden"] = bool(payload["is_hidden"])
    payload["is_tracked"] = bool(payload["is_tracked"])
    payload["display_name"] = (
        payload.get("friendly_name") or payload.get("last_host_name") or payload["mac"]
    )
    return payload
