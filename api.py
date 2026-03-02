from contextlib import asynccontextmanager
from threading import Event, Thread
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException

from config import get_settings
from backend import RouterClient
from ingest import ingest_html_snapshot
from db import connect, init_db

STATE: Dict[str, Any] = {
    "last_ingest": None,
    "last_result": None,
    "last_error": None,
}
settings = get_settings()


def require_token(x_token: Optional[str]) -> None:
    if x_token != settings.api_token:
        raise HTTPException(status_code=401, detail="bad token")


def poll_loop(stop_event: Event) -> None:
    client = RouterClient(settings.base_url, settings.router_username, settings.router_password)

    while not stop_event.is_set():
        try:
            html = client.fetch_connected_devices_html()
            result = ingest_html_snapshot(settings.db_path, html)
            STATE["last_ingest"] = result.get("seen_at")
            STATE["last_result"] = result
            STATE["last_error"] = None
        except Exception as e:
            STATE["last_error"] = str(e)
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


@app.get("/health")
def health():
    return {
        "ok": STATE["last_error"] is None,
        "last_ingest": STATE["last_ingest"],
        "last_error": STATE["last_error"],
        "poll_seconds": settings.poll_seconds,
    }


@app.get("/devices/latest")
def devices_latest(x_token: Optional[str] = Header(default=None)):
    require_token(x_token)

    conn = connect(settings.db_path)
    init_db(conn)

    try:
        # latest timestamp in observations
        row = conn.execute("SELECT MAX(seen_at) AS seen_at FROM observations").fetchone()
        if not row or not row["seen_at"]:
            raise HTTPException(status_code=503, detail=STATE["last_error"] or "no data yet")

        seen_at = row["seen_at"]

        devices = conn.execute(
            """
            SELECT
              o.mac, o.status, o.host_name, o.dhcp_mode, o.rssi_dbm, o.connection_type,
              o.ipv4, o.ipv6_global, o.ipv6_linklocal
            FROM observations o
            WHERE o.seen_at = ?
            ORDER BY o.status DESC, o.host_name
            """,
            (seen_at,),
        ).fetchall()
    finally:
        conn.close()

    return {
        "seen_at": seen_at,
        "count": len(devices),
        "devices": [dict(d) for d in devices],
    }
