# xfinity-device-tracker

Something I'm building to help track devices on my local network. This works with my gateway, so your mileage may vary. The current target is a standard Xfinity gateway (modem/wireless router combo unit) with the classic web UI.

## Requirements
- Python `3.12+`
- `pip`
- Dependencies in `requirements.txt`
- Test/dev dependencies in `requirements-dev.txt`

## Run
- Backend API:
  - `uvicorn api:app --host 0.0.0.0 --port 8000`
- Frontend web UI (Vite + Vanilla TS):
  - `cd frontend`
  - `cp .env.example .env` (PowerShell: `Copy-Item .env.example .env`)
  - `npm install`
  - `npm run dev`
  - Open from another machine: `http://<host-machine-ip>:5173`

## Environment Variables
- `ROUTER_IP` (required)
- `ROUTER_USERNAME` (required)
- `ROUTER_PASSWORD` (required)
- `DB_PATH` (optional, default `router.db`)
- `POLL_SECONDS` (optional, default `60`)
- `API_TOKEN` (optional, default `changeme`)
- `CORS_ORIGINS` (optional, comma-separated list)
  - Default supports local dev origins: `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:3000`, `http://127.0.0.1:3000`

## API Auth
- Protected endpoints require header:
  - `X-Token: <API_TOKEN>`

## API Contract

### `GET /health`
- Auth: no
- Purpose: ingestion loop status and recent failures
- Response example:
```json
{
  "ok": true,
  "last_ingest": "2026-03-02T23:22:19+00:00",
  "last_error": null,
  "last_error_at": null,
  "consecutive_failures": 0,
  "poll_seconds": 60
}
```

### `GET /devices/latest`
- Auth: yes (`X-Token`)
- Purpose: latest observation snapshot with merged device metadata
- Response example:
```json
{
  "seen_at": "2026-03-02T23:22:19+00:00",
  "count": 2,
  "devices": [
    {
      "mac": "AA:BB:CC:DD:EE:FF",
      "status": "online",
      "host_name": "example-device",
      "dhcp_mode": "DHCP",
      "rssi_dbm": -56,
      "connection_type": "Wi-Fi 2.4G",
      "ipv4": "192.168.1.42",
      "ipv6_global": null,
      "ipv6_linklocal": null,
      "friendly_name": "Office Sensor",
      "category": "iot",
      "notes": "Example note",
      "is_hidden": false,
      "is_tracked": true,
      "last_host_name": "example-device",
      "first_seen": "2026-03-02T22:00:00+00:00",
      "last_seen": "2026-03-02T23:22:19+00:00",
      "display_name": "Office Sensor"
    }
  ]
}
```

### `GET /devices`
- Auth: yes (`X-Token`)
- Purpose: alias for `/devices/latest` (same response shape)

### `PATCH /devices/{mac}`
- Auth: yes (`X-Token`)
- Purpose: update device metadata fields
- Request body:
  - `friendly_name` (string or `null`)
  - `category` (string or `null`)
  - `notes` (string or `null`)
  - `is_hidden` (boolean)
  - `is_tracked` (boolean)
  - At least one field must be provided
- Request example:
```json
{
  "friendly_name": "Office Sensor",
  "category": "iot",
  "notes": "Example note",
  "is_hidden": false,
  "is_tracked": true
}
```
- Response example:
```json
{
  "mac": "AA:BB:CC:DD:EE:FF",
  "first_seen": "2026-03-02T22:00:00+00:00",
  "last_seen": "2026-03-02T23:22:19+00:00",
  "last_host_name": "example-device",
  "notes": "Example note",
  "friendly_name": "Office Sensor",
  "category": "iot",
  "is_hidden": false,
  "is_tracked": true,
  "display_name": "Office Sensor"
}
```

## Frontend Notes
- Frontend defaults `VITE_API_BASE_URL=/api`, which is proxied by Vite to backend `http://127.0.0.1:8000`.
- For direct API calls (without Vite proxy), include your frontend origin in `CORS_ORIGINS`.
- Include `X-Token` header on all `/devices*` calls.
- Use `display_name` for labels in UI.
