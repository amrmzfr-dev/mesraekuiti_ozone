# Ozone Telemetry Backend API (Django)

Base URL examples
- Local dev: http://localhost:8000
- Deployed: https://your-domain

All new device → server calls use JSON over HTTPS.

## Authentication
- Device endpoints use Bearer token (obtained via /api/handshake).
- Header:
  - Authorization: Bearer <token>
  - Content-Type: application/json

## 1) Device Handshake
POST /api/handshake/
Request (JSON):
```
{
  "mac": "EC:E3:34:46:2B:C0",
  "firmware": "1.0.0"
}
```
Success Response (JSON):
```
{
  "device_id": "esp32-001",
  "token": "<random-token>",
  "assigned": true
}
```
Notes:
- If `assigned` is false, admin must assign this MAC a device_id first.

## 2) Ingest Treatment Event (Idempotent)
POST /api/events/
Headers:
- Authorization: Bearer <token>
- Content-Type: application/json

Request (JSON):
```
{
  "device_id": "esp32-001",
  "firmware": "1.0.0",
  "event_id": "esp32-001-0000000123",
  "event": "treatment",
  "treatment": "BASIC",
  "counter": 124,
  "ts": "2025-09-16T12:34:56Z"
}
```
Success Response (JSON):
```
{
  "ack": true,
  "event_id": "esp32-001-0000000123"
}
```
Rules:
- Duplicate `event_id` returns the same `ack` 200 without creating a new row.
- `treatment` ∈ { BASIC, STANDARD, PREMIUM }
- `counter` is the counter value at press time (billing on press).

## 3) Legacy Ingest (Form-URLENCODED)
POST /api/iot/
Content-Type: application/x-www-form-urlencoded

Body fields:
- mode: BASIC|STANDARD|PREMIUM|status
- macaddr: EC:E3:34:46:2B:C0
- type1, type2, type3
- count1, count2, count3
- timestamp: "2024-01-15 14:30:25"

Response: `{ "status": "ok", "id": <int> }`

## 4) Query Events (Admin/UI)
GET /api/events/?device_id=esp32-001&days=7&exclude_status=true

Response: JSON list of events.

## 5) Device Status
- Online devices: GET /api/devices/online/
- All devices: GET /api/devices/all/

## 6) Export CSV
GET /api/export/?device_id=esp32-001&days=30

Response: CSV download.

## 7) Admin: Register Device to Outlet/Machine
POST /api/machines/register/
Request (JSON):
```
{
  "device_id": "esp32-001",
  "outlet_id": 1,
  "name": "Machine A"
}
```

## Postman Quick Start
1) Handshake to get `token`
- Method: POST
- URL: http://localhost:8000/api/handshake/
- Headers: Content-Type: application/json
- Body (raw JSON):
```
{
  "mac": "EC:E3:34:46:2B:C0",
  "firmware": "1.0.0"
}
```
Example success response:
```
{
  "device_id": "esp32-001",
  "token": "REPLACE_WITH_TOKEN_FROM_RESPONSE",
  "assigned": true
}
```

2) Events ingest
- Method: POST
- URL: http://localhost:8000/api/events/
- Headers:
  - Authorization: Bearer REPLACE_WITH_TOKEN_FROM_HANDSHAKE
  - Content-Type: application/json
- Body (raw JSON):
```
{
  "device_id": "esp32-001",
  "firmware": "1.0.0",
  "event_id": "esp32-001-0000000123",
  "event": "treatment",
  "treatment": "BASIC",
  "counter": 124,
  "ts": "2025-09-16T12:34:56Z"
}
```
Notes:
- Change `event_id` every request to test idempotency (reusing returns ack without duplicate rows).
- `treatment` can be BASIC, STANDARD, or PREMIUM.

3) Verify
- GET http://localhost:8000/api/events/?device_id=esp32-001&exclude_status=true
- GET http://localhost:8000/api/devices/online/

## Notes
- All times are ISO8601 Z (UTC). Server falls back to server time if `ts` missing.
- Idempotency is enforced on `event_id`.
- Token rotation supported by updating `Device.token` in admin.
