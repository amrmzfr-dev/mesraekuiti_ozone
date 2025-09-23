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
======================================================================= DATA MODELS ===========================================================================
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
=========================================================== SECURITY CONSIDERATIONS ==========================================================================
===============================================================================================================================================================

- Device tokens should be rotated periodically
- Admin endpoints require authentication
- Consider implementing rate limiting for production
- Validate all input data
- Use HTTPS in production
- Implement proper CORS policies