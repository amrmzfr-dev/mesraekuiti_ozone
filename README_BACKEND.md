Ozone Telemetry Backend — Version 2025-09-25T14:50Z

Overview
This repository contains the Django backend for the Ozone telemetry platform. It manages device authentication, event ingestion, command delivery to ESP32 devices, status tracking, outlet/machine management, and web dashboards.

What’s New in This Stamped Version
- Device status is based on ESP32 polling (last_poll) with thresholds: Online (≤16 min), Idle (≤1 hr), Offline (>1 hr)
- Backend-to-ESP32 command system (queue, polling, results)
- Current counters from ESP32 supported in events and command results and reflected in UI
- Treatment logs per machine (with cumulative counters and reset entries) + smooth auto-refresh without scroll jumps
- Outlets table now auto-refreshes like devices/machines
- Machines page: assign/unassign to outlets, view treatment logs, delete machine
- Devices page: Outlet column added, MAC column removed, View/Quick Command removed, Commands retained
- Fixes for device assignment, admin config, and UI flicker

Tech Stack
- Django 5
- Django REST Framework
- HTMX + vanilla JS for dynamic tables
- SQLite (default)

Project Structure (backend)
- ozontelemetry/ — Django project
- telemetry/ — App with models, APIs, views, templates
  - api/ingest.py — devices API (handshake, events, devices data)
  - api/commands.py — command polling and result reporting
  - templates/ — dashboards and management UIs

Data Models (key fields)
- Device
  - device_id (MAC), mac, token, assigned, firmware, last_seen
  - OneToOne to Machine via Machine.device
- Machine
  - machine_id, machine_code/name, outlet (FK), device (OneToOne)
- Outlet
  - outlet_id, outlet_name, region
- DeviceStatus
  - device_id, wifi_connected, current_count_basic/standard/premium, last_seen, last_poll, device_timestamp
- TelemetryEvent
  - device_id, event_id, event, treatment, counter, event_type, count_basic/standard/premium, occurred_at, device_timestamp, wifi_status, payload
- Command
  - command_id (unique), device (FK), command_type, priority, payload, description, status (pending/sent/executed/failed/timeout), created_at, sent_at, executed_at, response_data, error_message, retry_count, created_by, expires_at

Device Status Logic (last_poll-first)
- Prefer DeviceStatus.last_poll (updated when ESP32 polls commands)
- Fallback to DeviceStatus.last_seen (updated on events/results)
- Thresholds: online ≤ 16min, idle ≤ 1hr, offline > 1hr

ESP32 Flow
1) Handshake
   - POST /api/handshake/
   - Body: mac, firmware
   - Returns: { device_id, token, assigned }
   - Save token persistently on ESP32
2) Poll Commands (requires assignment + Bearer token)
   - GET /api/device/{device_id}/commands/
   - Header: Authorization: Bearer <token>
   - Response items include both id and command_id
3) Execute and Report Result
   - POST /api/device/{device_id}/commands/{command_id}/
   - Body: { success, message?, response_data?, current_counters? }
4) Events (treatments)
   - POST /api/device/events/
   - Body: { device_id, event_id, event:"treatment", treatment: BASIC|STANDARD|PREMIUM, counter, ts, current_counters? }
   - If current_counters present, DeviceStatus counters are updated as source of truth

Web Pages (selected)
- /devices/ — devices list (status, assignment, outlet, commands link)
- /machines/ — machines list (outlet, device, counters, status) with Assign/Unassign, View Logs, Delete
- /machines/{machine_id}/logs/ — treatment logs page with:
  - Unified Machine Stats card: historical totals and current counters
  - Log table: treatment and reset entries with Basic/Standard/Premium columns
  - Auto-refresh via JSON API without scroll jump
- /outlets/ — outlets list with per-outlet totals, auto-refresh

APIs
- Devices and Events
  - POST /api/handshake/
  - POST /api/device/events/ (alias of /api/events/)
  - GET  /api/devices/ — devices data for UI (includes bound_machine with outlet_name)
  - GET  /api/devices/online/
- Commands
  - GET  /api/device/{device_id}/commands/ — ESP32 polls, marks sent, updates last_poll
  - POST /api/device/{device_id}/commands/{command_id}/ — ESP32 reports result; updates counters/last_seen
  - POST /api/device/{device_id}/commands/create/ — staff-only create via API
  - GET  /api/device/{device_id}/commands/status/ — staff-only command status
  - POST /api/commands/bulk/ — staff-only bulk create
  - POST /api/commands/{command_id}/retry/ — staff-only retry
- Machine Management & Logs
  - POST /machines/{machine_id}/assign/ (web)
  - POST /machines/{machine_id}/unassign/ (web)
  - POST /machines/{machine_id}/delete/ (web)
  - GET  /api/machines/{machine_id}/logs/ — JSON for auto-refresh on logs page

Counters & Treatment Logs
- Historical totals come from TelemetryEvent (never deleted): used for analytics
- Current counters live in DeviceStatus and reflect true device state (updated by events current_counters or reset results)
- Machine logs show cumulative Basic/Standard/Premium per row:
  - Computed in the browser by walking logs chronologically
  - Uses payload.current_counters when available; on RESET uses 0/0/0 (or response current_counters)

Security & Auth
- Commands endpoints require Bearer token from handshake and assigned=True
- Handshake returns token; device must persist and attach it
- Admin-only command creation/status/retry/bulk endpoints

Setup
1) Install
   - Python 3.13, pip install -r requirements.txt (create one if needed)
2) Run migrations
   - python manage.py migrate
3) Create superuser (optional)
   - python manage.py createsuperuser
4) Run server
   - python manage.py runserver

Quick Test Flow
1) Handshake: POST /api/handshake/ with mac, firmware
2) Assign device to machine via web UI (/devices/ or /machines/)
3) ESP32 polls commands with Bearer token
4) Send command from web UI (device detail → Commands)
5) ESP32 executes and reports result (optionally with current_counters)
6) Post treatment events with current_counters to keep backend in sync

Known UX Details
- Tables auto-refresh every second (devices, machines, outlets) or 5s (logs) without scroll jumps
- Initial “Loading...” placeholders prevent flicker
- Status badges: online (green), idle (yellow), offline (red), loading (gray)

Troubleshooting
- 401 on commands: device not assigned, missing/invalid Bearer token, or device_id mismatch
- Counters not updating: ensure ESP32 sends current_counters in events and on reset results
- Outlet name on devices list: comes from devices API bound_machine.outlet_name

Change Log (highlights)
- Fixed silent device assignment failure (RelatedObjectDoesNotExist)
- Corrected admin Outlet configuration
- Added Command model and API with dual id/command_id fields for ESP32 compatibility
- Updated ingest to accept current_counters and update DeviceStatus
- Added last_poll to DeviceStatus; status uses poll first
- Devices/Machines/Outlets tables unified behavior and reduced flicker
- Treatment logs page with cumulative counters and reset entries + smooth refresh
- Machines can be assigned/unassigned, and deleted from UI

License
Proprietary — internal project.

===============================================================================================================================================================
=========================================================== OZONE TELEMETRY BACKEND API (DJANGO) =============================================================
===============================================================================================================================================================

===============================================================================================================================================================
========================================================================= BASE URLs ===========================================================================
===============================================================================================================================================================
- **Local Development**: `http://localhost:8000`
- **Production**: `https://your-domain.com`

===============================================================================================================================================================
=================================================================== PROJECT STRUCTURE (BACKEND) ===============================================================
===============================================================================================================================================================
- `backend/ozontelemetry/` — Django project (settings, urls)
- `backend/telemetry/` — App
  - `api/`
    - `ingest.py` — device ingest, handshake, export, flush, devices-data
    - `stats.py` — analytics/statistics APIs
  - `views/`
    - `viewsets.py` — DRF viewsets for telemetry, devices, outlets, machines
  - `auth_views.py` — auth endpoints (login/logout/register/user/check)
  - `models.py`, `serializers.py`

Notes:
- Pure API only; no HTML/template endpoints are exposed.

===============================================================================================================================================================
======================================================================= AUTHENTICATION ========================================================================
===============================================================================================================================================================
- **Device endpoints**: Bearer token authentication (obtained via `/api/handshake/`)
- **Admin/User endpoints**: Django session authentication with cookies
- **Headers**:
  - `Authorization: Bearer <token>` (for device APIs)
  - `Content-Type: application/json`
  - `credentials: include` (for session-based APIs)

---

===============================================================================================================================================================
==================================================================== AUTHENTICATION APIS ======================================================================
===============================================================================================================================================================

### 1. User Login
**POST** `/api/auth/login/`
- **Purpose**: User authentication for admin/frontend access
- **Request Body** (JSON):
```json
{
  "username": "admin",
  "password": "password"
}
```
- **Response** (JSON):
```json
{
  "success": true,
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@example.com",
    "first_name": "",
    "last_name": "",
    "is_staff": true,
    "is_superuser": true
  }
}
```

### 2. User Logout
**POST** `/api/auth/logout/`
- **Purpose**: Logout current user
- **Response** (JSON):
```json
{
  "success": true,
  "message": "Successfully logged out"
}
```

### 3. User Registration
**POST** `/api/auth/register/`
- **Purpose**: Register new user
- **Request Body** (JSON):
```json
{
  "username": "newuser",
  "password": "password123",
  "email": "user@example.com",
  "first_name": "John",
  "last_name": "Doe"
}
```
- **Response** (JSON):
```json
{
  "success": true,
  "message": "User created successfully",
  "user": {
    "id": 2,
    "username": "newuser",
    "email": "user@example.com",
    "first_name": "John",
    "last_name": "Doe"
  }
}
```

### 4. Get User Info
**GET** `/api/auth/user/`
- **Purpose**: Get current authenticated user information
- **Response** (JSON):
```json
{
  "success": true,
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@example.com",
    "first_name": "",
    "last_name": "",
    "is_staff": true,
    "is_superuser": true
  }
}
```

### 5. Check Authentication Status
**GET** `/api/auth/check/`
- **Purpose**: Check if user is currently authenticated
- **Response** (JSON):
```json
{
  "authenticated": true,
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@example.com",
    "first_name": "",
    "last_name": "",
    "is_staff": true,
    "is_superuser": true
  }
}
```

---

===============================================================================================================================================================
================================================================== DEVICE MANAGEMENT APIS ====================================================================
===============================================================================================================================================================

### 1. Device Handshake
**POST** `/api/handshake/`
- **Purpose**: Device registration and token acquisition
- **Request Body** (JSON):
```json
{
  "mac": "EC:E3:34:46:2B:C0",
  "firmware": "1.0.0"
}
```
- **Response** (JSON):
```json
{
  "device_id": "esp32-001",
  "token": "<random-token>",
  "assigned": true
}
```
- **Notes**: 
  - If `assigned` is `false`, admin must assign device_id first
  - Creates DeviceStatus entry automatically

### 2. Device Events (Idempotent)
**POST** `/api/device/events/`
- **Headers**: `Authorization: Bearer <token>`
- **Request Body** (JSON):
```json
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
- **Response** (JSON):
```json
{
  "ack": true,
  "event_id": "esp32-001-0000000123"
}
```
- **Rules**:
  - Duplicate `event_id` returns same `ack` without creating new row
  - `treatment` ∈ {BASIC, STANDARD, PREMIUM}
  - `counter` is billing value at press time

### 3. Legacy IoT Ingest
**POST** `/api/iot/`
- **Content-Type**: `application/x-www-form-urlencoded`
- **Body Fields**:
  - `mode`: BASIC|STANDARD|PREMIUM|status
  - `macaddr`: EC:E3:34:46:2B:C0
  - `type1`, `type2`, `type3`: On-time values
  - `count1`, `count2`, `count3`: Counter values
  - `timestamp`: "2024-01-15 14:30:25"
  - `rtc_available`: true/false (optional)
  - `sd_available`: true/false (optional)
- **Response**: `{"status": "ok"}`

---

===============================================================================================================================================================
===================================================================== DATA QUERY APIS =========================================================================
===============================================================================================================================================================

### 4. Telemetry Events
**GET** `/api/events/`
- **Query Parameters**:
  - `device_id`: Filter by device
  - `days`: Number of days to look back (default: 7)
  - `exclude_status`: true/false (exclude heartbeat events)
- **Response**: JSON list of events

### 5. Device Status
**GET** `/api/devices/online/`
- **Response**: List of devices online in last 5 minutes

- need to add checking poll, on the esp32

**GET** `/api/devices/all/`
- **Response**: List of all devices (online and offline)

**GET** `/api/devices-data/`
- **Purpose**: Real-time devices data for UI
- **Response**: JSON with device status and counts

### 6. Telemetry Summary
**GET** `/api/telemetry/summary/`
- **Query Parameters**: `device_id`
- **Response**: Latest device status with counts and mode

**GET** `/api/telemetry/latest/`
- **Query Parameters**: `device_id`
- **Response**: Most recent telemetry data

---

===============================================================================================================================================================
================================================================== OUTLET MANAGEMENT APIS =====================================================================
===============================================================================================================================================================

### 7. Outlets CRUD
**GET** `/api/outlets/`
- **Query Parameters**:
  - `is_active`: true/false (filter by status)
- **Response**: List of outlets

**POST** `/api/outlets/`
- **Request Body** (JSON):
```json
{
  "name": "Outlet Name",
  "address": "Address",
  "contact_person": "Contact Name",
  "is_active": true
}
```

**GET** `/api/outlets/{id}/`
- **Response**: Single outlet details

**PUT** `/api/outlets/{id}/`
- **Request Body**: Updated outlet data

**DELETE** `/api/outlets/{id}/`
- **Response**: Deletes outlet

---

===============================================================================================================================================================
================================================================= MACHINE MANAGEMENT APIS =====================================================================
===============================================================================================================================================================

### 8. Machines CRUD
**GET** `/api/machines/`
- **Query Parameters**:
  - `outlet_id`: Filter by outlet
  - `is_active`: true/false
  - `device_id`: Filter by current device
- **Response**: List of machines

**POST** `/api/machines/`
- **Request Body** (JSON):
```json
{
  "outlet": 1,
  "name": "Machine Name",
  "is_active": true
}
```

**GET** `/api/machines/{id}/`
- **Response**: Single machine details

**PUT** `/api/machines/{id}/`
- **Request Body**: Updated machine data

**DELETE** `/api/machines/{id}/`
- **Response**: Deletes machine

### 9. Machine Device Registration
**POST** `/api/machines/register/`
- **Request Body** (JSON):
```json
{
  "device_id": "esp32-001",
  "outlet_id": 1,
  "name": "Machine A"
}
```
- **Response**: Created machine with device binding

**GET** `/api/machines/unregistered/`
- **Response**: Devices with telemetry data but not registered as machines

---

===============================================================================================================================================================
============================================================== ANALYTICS & STATISTICS APIS ====================================================================
===============================================================================================================================================================

### 10. Usage Statistics
**GET** `/api/test/stats/`
- **Query Parameters**:
  - `outlet_id`: Filter by outlet
  - `machine_id`: Filter by machine
  - `device_id`: Filter by device
  - `granularity`: minute|hour|day|month (default: day)
  - `start`, `end`: ISO date/time
  - `days`: Number of days (default: 7)
  - `cumulative`: true/false (cumulative data)
  - `ma`: Moving average window (0=off)
  - `compare`: true/false (compare with previous period)
- **Response**: Aggregated usage stats with labels and series

**GET** `/api/test/stats-options/`
- **Query Parameters**:
  - `outlet_id`: Get machines for outlet
  - `machine_id`: Get devices for machine
- **Response**: Filter options (outlets, machines, devices)

**GET** `/api/test/stats-export.csv`
- **Purpose**: Export current filtered stats as CSV
- **Response**: CSV download

### 11. Events Analytics
**GET** `/api/events/analytics/`
- **Query Parameters**:
  - `device_id`: Filter by device
  - `days`: Number of days
- **Response**: Aggregated analytics data

---

===============================================================================================================================================================
=============================================================== EXPORT & UTILITY APIS =========================================================================
===============================================================================================================================================================

### 12. Data Export
**GET** `/api/export/`
- **Query Parameters**:
  - `device_id`: Filter by device
  - `days`: Number of days (default: 30)
- **Response**: CSV download

### 13. Data Management
**POST** `/api/flush/`
- **Purpose**: Flush all telemetry data (admin only)
- **Response**: Confirmation

---

===============================================================================================================================================================
==================================================================== DATA MODELS ==============================================================================
===============================================================================================================================================================

### Device
- `mac`: MAC address (unique)
- `device_id`: Device identifier (unique)
- `token`: Bearer token for authentication
- `assigned`: Whether device is assigned by admin
- `firmware`: Firmware version
- `last_seen`: Last communication timestamp
- `notes`: Admin notes

### TelemetryEvent
- `device_id`: Device identifier
- `event_type`: Legacy type used by older flows (BASIC|STANDARD|PREMIUM|status)
- `event_id`: Unique event identifier (for idempotency)
- `event`: Event type (e.g., "treatment")
- `treatment`: BASIC|STANDARD|PREMIUM
- `counter`: Counter value at press time
- `occurred_at`: Event timestamp
- `device_timestamp`: Device-provided timestamp
- `wifi_status`: WiFi connection status
- `payload`: Additional JSON data
- Legacy counters (may be null): `count_basic`, `count_standard`, `count_premium`

### DeviceStatus
- `device_id`: Device identifier (unique)
- `last_seen`: Last communication timestamp
- `wifi_connected`: WiFi connection status
- `rtc_available`: RTC availability
- `sd_card_available`: SD card availability
- `current_count_basic`: Current basic count
- `current_count_standard`: Current standard count
- `current_count_premium`: Current premium count
- `uptime_seconds`: Device uptime
- `device_timestamp`: Device timestamp

### Outlet
- `name`: Outlet name
- `address`: Physical address
- `contact_person`: Contact person
- `is_active`: Active status
- Owner-maintained metrics (optional):
  - `total_sva`: Total Service Advisors
  - `average_intage_services`: Average intage services
  - `number_of_machines`: Number of machines at outlet

### Machine
- `outlet`: Associated outlet
- `name`: Machine name
- `is_active`: Active status

### MachineDevice
- `machine`: Associated machine
- `device_id`: Device identifier
- `is_active`: Active binding status
- `assigned_date`: Assignment date
- `deactivated_date`: Deactivation date

---

===============================================================================================================================================================
============================================================== QUICK START EXAMPLES ==========================================================================
===============================================================================================================================================================

### 1. User Authentication
```bash
# 1. Login to get session cookie
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -c cookies.txt \
  -d '{"username": "admin", "password": "password"}'

# 2. Check authentication status
curl http://localhost:8000/api/auth/check/ \
  -b cookies.txt

# 3. Get user info
curl http://localhost:8000/api/auth/user/ \
  -b cookies.txt

# 4. Logout
curl -X POST http://localhost:8000/api/auth/logout/ \
  -b cookies.txt
```

### 2. Device Registration & Event Submission
```bash
# 1. Handshake to get token
curl -X POST http://localhost:8000/api/handshake/ \
  -H "Content-Type: application/json" \
  -d '{"mac": "EC:E3:34:46:2B:C0", "firmware": "1.0.0"}'

# 2. Submit treatment event
curl -X POST http://localhost:8000/api/device/events/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "esp32-001",
    "firmware": "1.0.0",
    "event_id": "esp32-001-0000000123",
    "event": "treatment",
    "treatment": "BASIC",
    "counter": 124,
    "ts": "2025-09-16T12:34:56Z"
  }'
```

### 3. Query Device Data (Authenticated)
```bash
# Get online devices (requires authentication)
curl http://localhost:8000/api/devices/online/ \
  -b cookies.txt

# Get events for device
curl "http://localhost:8000/api/events/?device_id=esp32-001&days=7" \
  -b cookies.txt

# Get device summary
curl "http://localhost:8000/api/telemetry/summary/?device_id=esp32-001" \
  -b cookies.txt
```

### 4. Machine Management (Authenticated)
```bash
# Register device as machine
curl -X POST http://localhost:8000/api/machines/register/ \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "device_id": "esp32-001",
    "outlet_id": 1,
    "name": "Machine A"
  }'

# Get machines for outlet
curl "http://localhost:8000/api/machines/?outlet_id=1" \
  -b cookies.txt
```

### 5. Analytics & Statistics (Authenticated)
```bash
# Get usage statistics
curl "http://localhost:8000/api/test/stats/?days=7&granularity=day" \
  -b cookies.txt

# Get filter options
curl "http://localhost:8000/api/test/stats-options/" \
  -b cookies.txt

# Export statistics as CSV
curl "http://localhost:8000/api/test/stats-export.csv?days=30" \
  -b cookies.txt \
  -o stats_export.csv
```

---

===============================================================================================================================================================
=========================================================================== NOTES ============================================================================
===============================================================================================================================================================

- **Time Format**: All timestamps use ISO8601 Z (UTC) format
- **Idempotency**: Event submission is idempotent based on `event_id`
- **Token Rotation**: Supported by updating `Device.token` in admin
- **CORS**: Configured for cross-origin requests from frontend
- **Rate Limiting**: No rate limiting implemented (consider for production)
- **Data Retention**: No automatic data cleanup (implement as needed)

===============================================================================================================================================================
================================================================== SECURITY CONSIDERATIONS ====================================================================
===============================================================================================================================================================

- Device tokens should be rotated periodically
- Admin endpoints require authentication
- Consider implementing rate limiting for production
- Validate all input data
- Use HTTPS in production
- Implement proper CORS policies

===============================================================================================================================================================
===================================================================== CURRENT STATUS (2025-09-25) ==============================================================
===============================================================================================================================================================

### ✅ WORKING FEATURES:
- **Device Authentication**: Bearer token system working correctly
- **Device Assignment**: Web interface assignment now works (fixed RelatedObjectDoesNotExist bug)
- **Event Ingestion**: ESP32 devices can post events with proper authentication
- **Device Management**: Full CRUD operations for devices, machines, outlets
- **Analytics**: Statistics and analytics APIs functional
- **User Authentication**: Session-based auth for web interface

### 🔧 RECENT FIXES:
- **Device Assignment Bug**: Fixed silent failure in web assignment due to RelatedObjectDoesNotExist exception
- **Authentication Flow**: Device events endpoint now properly authenticates assigned devices
- **Relationship Management**: Bidirectional Device-Machine relationships working correctly

### 📊 CURRENT DATABASE STATE:
- **Devices**: 1 device (3C:8A:1F:A4:22:D4) - ASSIGNED ✅
- **Machines**: 1 machine (CH1/027/2024) - HAS DEVICE ✅
- **Assignment Status**: 1 assigned device, 0 unassigned devices
- **Authentication**: Device can authenticate with Bearer token

### 🚀 RECENTLY IMPLEMENTED:
- **Command System**: Complete backend-to-ESP32 command architecture ✅
- **Command Queue**: Pending commands management ✅
- **Command API**: Polling and execution tracking ✅
- **Web Command Interface**: Command management UI ✅
- **Current Counters Support**: ESP32 can send complete counter state ✅
- **Reset Command Integration**: Backend updates counters on reset ✅
- **Improved Device Status**: Online (16min)/Idle (1hr)/Offline (>1hr) based on ESP32 polling ✅

===============================================================================================================================================================
================================================================== SECURITY CONSIDERATIONS ====================================================================
===============================================================================================================================================================

- Device tokens should be rotated periodically
- Admin endpoints require authentication
- Consider implementing rate limiting for production
- Validate all input data
- Use HTTPS in production
- Implement proper CORS policies