# Frontend (React + Vite + TypeScript)

This frontend provides dashboards and admin tools to visualize and test data flowing from ESP32 → Backend → Frontend.

## Prerequisites
- Node 18+
- Backend running locally (Django), default at http://localhost:8000/api

## Setup
```
cd frontend
npm install
```

Create `.env` (or `.env.local`) in `frontend/`:
```
VITE_API_BASE=http://localhost:8000/api
```

## Run
```
npm run dev
```
Open the URL shown by Vite (e.g. http://localhost:5173)

Login: `admin` / `admin` (local-only dummy)

## Pages
- Dashboard: system overview; devices, outlets, charts, recent events
- Outlets: list of outlets (uses GET /api/outlets/)
- Machines: list of machines (uses GET /api/machines/)
- Charts: detailed charts (uses GET /api/events/analytics/)
- Handshake: test device handshake; calls POST `/api/handshake/`, stores `token` and `device_id` in localStorage
- Send Event: test ingest; POST `/api/device/events/` (Bearer token). Sends treatment events with `event_id`, `treatment`, `counter`, `ts`

## API Alignment
- Device status: `GET /api/devices/all/` (used by Dashboard)
- Events list: `GET /api/events/?exclude_status=true` (Dashboard recent events)
- Analytics: `GET /api/events/analytics/?device_id=...&days=...` (Dashboard/Charts)
- Export: `GET /api/export/?device_id=...&days=...` (CSV)

## ESP32 → Backend → Frontend Flow
1) ESP32 sends only "treatment" events (on button press) with:
```
{
  "device_id": "esp32-001",
  "firmware": "1.0.0",
  "event_id": "esp32-001-0000000123",
  "event": "treatment",
  "treatment": "BASIC|STANDARD|PREMIUM",
  "counter": 124,
  "ts": "2025-09-16T12:34:56Z"
}
```
2) Backend stores idempotently and updates `DeviceStatus` and `UsageStatistics`.
3) Frontend pulls devices, events, and analytics via `/api/...` endpoints above.

## Notes
- Configure CORS on backend if serving frontend from a different origin
- Use HTTPS and secure auth in production
- Vite env var: `import.meta.env.VITE_API_BASE`
