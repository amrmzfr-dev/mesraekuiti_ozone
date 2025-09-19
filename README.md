## Ozone Machine Counter System (ESP32 + 20x4 I2C LCD)

This firmware powers an ozone machine counter-and-control panel built on an ESP32 with a 20x4 I2C LCD. It manages three treatment types (BASIC, STANDARD, PREMIUM) with per‑treatment timers, relays, and persistent counters stored in EEPROM. The UI is button‑driven and designed to be non‑blinking and robust for rental/production scenarios.

### Key Features
- 20x4 I2C LCD with clean, stable UI (no unnecessary redraw/blink)
- Three treatments:
  - BASIC (B)
  - STANDARD (S)
  - PREMIUM (P)
- Treatment timers: 5 min, 10 min, 15 min (B/S/P)
- Single relay channel (GPIO23) held ON for full treatment duration (all B/S/P)
- Per‑treatment counters persisted in EEPROM (survive power cycles)
- Start‑on‑press counting (counter increments immediately on button press, not at timer end)
- Long‑press stop during a running timer (PREMIUM button ≥ 2s)
- Wi‑Fi connectivity with local web configuration interface
- AP mode fallback for initial setup and configuration

---

## Hardware

### Controller
- Board: ESP32 DevKit (esp32dev)

### LCD
- 20 columns x 4 rows, HD44780 compatible via PCF8574/PCF8574A I2C backpack
- Typical I2C address: `0x27` or `0x3F` (this project uses `0x27`)
- I2C pins on ESP32:
  - SDA: GPIO 21
  - SCL: GPIO 22

### Buttons
- Module type: 2‑pin buttons to GND, with internal pull‑ups enabled
- Pins (repurposed as direct actions):
  - BASIC: GPIO 4 (formerly UP)
  - STANDARD: GPIO 14 (formerly DOWN)
  - PREMIUM: GPIO 15 (formerly SELECT)

Important: Avoid ESP32 bootstrap pins (e.g., GPIO0, GPIO2) for buttons due to boot mode interference and phantom presses.

### Relays / LEDs
- Relay pins (active HIGH expected):
  - BASIC (B): GPIO 23
  - STANDARD (S): GPIO 19
  - PREMIUM (P): GPIO 18

Wire each relay INx to the corresponding pin and ensure relay boards share GND with the ESP32.

Note (current deployment): Using a single relay channel for all treatments
- To simplify wiring, only Channel 1 (IN1 on the 4‑relay board) is used and driven by GPIO23.
- All treatments (B/S/P) energize the same relay; the ESP32 timer length determines how long the relay stays closed (5/10/15 minutes).
- IN2/IN3/IN4 remain unconnected.

### Power
- The LCD and relays are powered from 5V; ESP32 is powered via USB or regulated 5V input. Ensure sufficient current budget.

### Wi‑Fi
- ESP32 has built‑in Wi‑Fi capability
- Default AP mode: SSID `OZONE-CONFIG`, Password `mb95z78y`
- Default client mode: SSID `testtest`, Password `mb95z78y`
- Web interface accessible at `http://192.168.4.1` (AP mode) or device IP (client mode)

---

## Software

### Project
- PlatformIO (Arduino framework)
- `platformio.ini` includes:
  - `LiquidCrystal_I2C@^1.1.4`
  - `jm_PCF8574@^2.0.0` (kept in deps; current code uses `LiquidCrystal_I2C`)
  - `EEPROM@2.0.0`
  - `bblanchon/ArduinoJson@^7.0.4`
  - `monitor_speed = 115200`

### Source Structure
- **Main file**: `src/main.cpp` - Core system functionality (LCD, buttons, timers, relays, EEPROM)
- **Configuration**: `src/config.h` - Pin definitions, constants, and system parameters
- **Web Interface**: `src/web_interface.h/.cpp` - Wi-Fi and web server functionality

### Pin Map (code)
```
SDA=21, SCL=22
UP=4, DOWN=14, SELECT=15
RELAY_B=23, RELAY_S=19, RELAY_P=18
```

---

## Code Architecture

### Simple Structure
The codebase uses a clean, straightforward organization:

#### **Main File** (`main.cpp`)
- **Purpose**: Core system functionality in one place
- **Contains**:
  - LCD display operations and UI management
  - Button input handling and debouncing
  - Treatment timer logic and state management
  - Relay control and hardware abstraction
  - EEPROM data persistence
  - Main system loop and coordination

#### **Web Interface** (`web_interface.h/.cpp`)
- **Purpose**: Wi-Fi connectivity and web server
- **Contains**:
  - Wi-Fi connection management (STA/AP modes)
  - Web server setup and request handling
  - Configuration interface and JSON API
  - Wi-Fi credentials persistence

#### **Configuration** (`config.h`)
- **Purpose**: Centralized configuration and constants
- **Contains**:
  - Pin definitions and hardware settings
  - Timer durations and system parameters
  - Wi-Fi settings and EEPROM layout

### Benefits of Simple Structure
- **Simplicity**: Easy to understand and navigate
- **Maintainability**: All core functionality in one place
- **Readability**: Clear separation between core logic and web interface
- **Efficiency**: No unnecessary abstraction overhead
- **Debugging**: Easy to trace through the main flow

---

## Wi‑Fi Configuration

### Initial Setup
1. Power on the ESP32
2. Connect to Wi‑Fi network `OZONE-CONFIG` (password: `mb95z78y`)
3. Open web browser to `http://192.168.4.1`
4. Configure Wi‑Fi credentials and save
5. Device will restart and connect to your network

### Web Interface Features
- **Status Display**: Current Wi‑Fi mode, IP address, counter values, timer status
- **Wi‑Fi Configuration**: Change SSID and password
- **Device Monitoring**: Real‑time counter and system status
- **JSON API**: `/status` endpoint for programmatic access

### Default Credentials
- **AP Mode**: SSID `OZONE-CONFIG`, Password `mb95z78y`
- **Client Mode**: SSID `testtest`, Password `mb95z78y`

### EEPROM Storage
- Wi‑Fi SSID stored at address 20‑51 (32 bytes max)
- Wi‑Fi password stored at address 60‑123 (64 bytes max)
- Credentials persist across power cycles

---

## UI & Behavior

### Main Page (20x4)
- Row 0: "OZONE MACHINE" (centered)
- Row 1: Counters in the format `0000 0000 0000` (B S P)
- Row 2: Labels ` B   S   P ` (no selection cursor; buttons are direct)
- Row 3: Instruction line `BASIC  STD  PREM`

Navigation (direct-start buttons):
- BASIC button (GPIO4): starts BASIC timer immediately
- STANDARD button (GPIO14): starts STANDARD timer immediately
- PREMIUM button (GPIO15): starts PREMIUM timer immediately

Counting rule (business logic):
- The counter increments immediately when SELECT starts a treatment.
- The counter does not increment again when the timer completes.

### Timer Page
- Row 0: "OZONE MACHINE"
- Row 1: Treatment name (centered precisely):
  - BASIC TREATMENT (15 chars)
  - STANDARD TREATMENT (17 chars)
  - PREMIUM TREATMENT (16 chars)
- Row 2: `MM:SS` countdown (only the digits update per second; text remains static)
- Row 3: blank

While timer is active:
- All start buttons are ignored.
- PREMIUM button long‑press (≥ 2s) stops the timer and returns to the main page.

### Reset
- Button-based reset is disabled.
- Staff can reset counters from the local `/settings` web UI (auth required).

---

## Timers

Current timings (Testing; milliseconds):
- BASIC: 5,000 ms (5 s)
- STANDARD: 10,000 ms (10 s)
- PREMIUM: 15,000 ms (15 s)

Note: Production values are 5/10/15 minutes. Switch back before deployment.

---

## EEPROM Persistence

Counters are stored in ESP32 EEPROM emulation and auto‑loaded on boot.

Layout:
- Address 0..3:  B counter (uint32_t)
- Address 4..7:  S counter (uint32_t)
- Address 8..11: P counter (uint32_t)
- Address 12..13: Magic number 0x1234 for data validity

When counters change (start of a treatment or after reset), values are saved immediately via `EEPROM.commit()`.

---

## Build & Upload

1) Install PlatformIO.

2) Connect ESP32 via USB. Confirm COM port in Windows Device Manager.

3) Build & upload:
```
pio run --target upload --upload-port COM3
```

If you see "Failed to connect to ESP32: Wrong boot mode detected" on some boards:
- Hold BOOT when flashing.
- Retry the upload command.

Serial monitor (optional):
```
pio device monitor -b 115200 --port COM3
```

---

## Troubleshooting

LCD shows backlight but no text:
- Verify I2C address (0x27 vs 0x3F)
- Adjust LCD contrast potentiometer on the backpack
- Confirm SDA=21 / SCL=22 wiring

Buttons not detected / phantom presses:
- Ensure INPUT_PULLUP is used and buttons go to GND
- Avoid boot‑strap pins (GPIO0, GPIO2)
- Verify with serial logs that button states toggle

Relays not switching:
- Ensure a common GND between relay module and ESP32
- Confirm relay board logic level compatibility and INx mapping

Display blinking:
 - This firmware minimizes redraws. If you add prints, avoid clearing full screen repeatedly; use partial updates (see `updateTimerDisplay()`).

---

## LCD Sleep

- The LCD backlight turns off after 2 minutes of inactivity on the main page.
- Any button press wakes the screen. The wake press does not navigate or start a treatment.
- The LCD never sleeps while a treatment timer is active.

---

## Code Structure (high level)

- `setup()`
  - Init I2C/LCD, buttons, relays
  - Init EEPROM and load counters
  - Draw initial main screen

- `loop()`
  - `handleButtons()` for navigation, start/stop, reset flow
  - `updateTimer()` if timer active
  - Periodic display updates (only when needed)

- Display
  - `updateDisplay()` draws main or timer views and the reset prompt
  - `updateTimerDisplay()` only updates the timer digits `MM:SS`

- Actions
  - `startTimer()` sets duration, activates relay, increments and saves counter
  - `stopTimer()` stops timer and deactivates relays
  - `resetAllCounters()` zeros counters and saves to EEPROM

- Persistence
  - `saveCountersToEEPROM()` / `loadCountersFromEEPROM()` with magic number validation

---

## Operational Notes

- Counters increment at treatment start (SELECT press), not on completion. This is intentional for billing integrity in rental scenarios.
- Navigation (UP/DOWN) is disabled during an active timer.
- SELECT long‑press (≥ 2s) only stops an active timer; it does nothing on the main page except starting a treatment with a short press.
- Reset requires two steps: 10s UP+DOWN hold, then SELECT to confirm (or DOWN to cancel).

---

## Customization

- Change button pins if your board differs; avoid GPIO0/GPIO2.
- Adjust LCD centering by altering `lcd.setCursor(col,row)` in `updateDisplay()`.
- Modify relay polarity if your hardware uses active‑LOW modules.

---

## License & Credits

- Uses `LiquidCrystal_I2C`, `jm_PCF8574`, and Arduino EEPROM emulation libraries.
- Project intended for embedded control/rental system use cases.


---

## NEXT PLAN / PROPOSED

### 2) Cloud logging API for treatment starts
- Goal: Report treatment button presses to a web backend for billing/auditing.
- Proposed events:
  - `treatment`: sent immediately on button press (includes B/S/P, counter value after increment, timestamp)
  - No completion events needed - we only care that the treatment was initiated

- Suggested HTTP interface (examples):
  - POST `/api/v1/ozone/events`
  - Headers: `Authorization: Bearer <token>`; `Content-Type: application/json`
  - Body example:
    ```json
    {
      "device_id": "esp32-001",
      "firmware": "1.0.0",
      "event_id": "esp32-001-0000000123",
      "event": "treatment",
      "treatment": "BASIC",
      "counter": 123,
      "ts": "2025-09-16T12:34:56Z"
    }
    ```

- Reliability plan (detailed):
  - Event identity (idempotency key):
    - Use a monotonic per‑device sequence combined with the device id: `event_id = <device_id>-<seq>` (e.g., `esp32-001-0000000123`).
    - Persist `seq` in NVS/EEPROM and increment atomically for each event append. On reboot, continue from the stored value.
    - Alternative: RFC4122 UUIDv4 (random) is acceptable but makes ordering harder and depends on RNG. Monotonic `seq` is preferred for simplicity and ordering.
  - Device identity (binding an ESP to `device_id`):
    - Provisioning options:
      - Factory programming: embed a unique `device_id` at build time; store in NVS on first boot.
      - First‑boot claim: ship a claim code/QR; on first Wi‑Fi connect, call `POST /api/v1/devices/claim` with the claim code to receive `{ device_id, token }` and store both in NVS.
      - Manual setup: set `device_id` over serial or a hidden button combo + captive portal config.
    - Store `device_id` and `token` in NVS (non‑volatile). The token is used for Authorization.
  - HTTP JSON schemas:
    - treatmenta:
      ```json
      {
        "device_id": "esp32-001",
        "firmware": "1.0.0",
        "event_id": "esp32-001-0000000123",
        "event": "treatment",
        "treatment": "BASIC",
        "counter": 123,
        "ts": "2025-09-16T12:34:56Z"
      }
      ```
    - Note: Only `treatment_started` events are sent. No completion events needed.
    - Server ACK (success):
      ```json
      { "ack": true, "event_id": "esp32-001-0000000123" }
      ```
    - Server duplicate handling:
      - Either return the same 200 OK with `{ack:true}` if the `event_id` already exists, or respond 409 Conflict with `{ack:true, event_id: "..."}`. The client treats both as acknowledged and deletes the local record.
  - Queueing & retry:
    - On every button press (BASIC/STANDARD/PREMIUM): append event JSON to an append‑only queue file (JSONL) in LittleFS/SPIFFS.
    - Background uploader sends the oldest event first. Only delete after a valid ACK echoing the same `event_id`.
    - Retries: exponential backoff starting at 2s, doubling up to 5 minutes, with ±20% jitter. One in‑flight request at a time.
    - Trigger uploads on: boot, Wi‑Fi connect, and when a new event is appended.
    - Timeouts: connect 3s, total request 10s. Treat network errors, 5xx, or malformed responses as retryable.
  - Storage management:
    - Soft cap queue file to 1–4 MB. If capacity approached, continue to retain events and surface a local warning (serial/LED). Do not drop events.
    - Periodically compact the queue when drained or when fragmentation is high.
  - Clock & timestamps:
    - Prefer RTC (DS3231). Store/send times in UTC ISO‑8601. If RTC invalid, optionally use NTP after Wi‑Fi connect to seed RTC.
  - Security:
    - Use HTTPS. Include `Authorization: Bearer <token>` in each request. Rotate tokens via server policy; store new token in NVS.

### 3) Add RTC for accurate timestamping (no LCD dependency)
- Goal: Use an RTC to provide stable timestamps for event logs (independent from Wi‑Fi NTP). LCD is not involved.
- Suggested module: `DS3231` (I2C), known for high accuracy.
- Wiring (dedicated I2C bus, not shared with LCD):
  - RTC SDA → GPIO25 (Wire1 SDA)
  - RTC SCL → GPIO26 (Wire1 SCL)
  - RTC VCC → 3.3V
  - RTC GND → GND
  - Optional SQW/INT → GPIO27 (for 1Hz tick/alarms)
  - I2C address: 0x68
- Firmware plan:
  - On boot: try to read RTC time; if invalid, fall back to NTP (if available) and set RTC once.
  - At event time: read timestamp from RTC and include in API payloads.
  - Add a maintenance command or hidden combo to set RTC time from serial if needed.
  - Initialize second bus in code: `Wire1.begin(25, 26);` and use an RTC lib that supports a custom TwoWire instance.

### 4) Security & device identity
- Provision a unique `device_id` and API token per device.
- Store token in NVS/EEPROM securely; consider rotating tokens.
- Use HTTPS (TLS) for all transmissions.

### 4.1) Provisioning & Local Configuration (Recommended Flow)

Goal: Before renting, bind each ESP32 to a known identity in your system and capture deployment‑specific settings without reflashing firmware.

Decision: Server-assigned device IDs with manual admin assignment
- ESP32 sends its MAC address to server on first boot (via handshake API)
- Server admin manually assigns `device_id` (e.g., `esp32-001`, `esp32-002`) in the admin system
- Server returns the assigned `device_id` and `token` to ESP32
- ESP32 stores the server-assigned `device_id` in NVS (read-only in UI)
- Wi‑Fi credentials and API base are written via staging jig or staff web UI
- A local staff web UI is available at `/settings` for maintenance (auth‑protected). In AP mode: `http://192.168.4.1/settings`. In Wi‑Fi client mode: `http://<device-ip>/settings`.

Provisioning flow:
1. **ESP32 first boot:**
   - ESP32 calls `POST /api/v1/devices/register` with `{ mac_address, firmware_version }`
   - Server responds with `{ status: "pending_assignment" }` (no device_id yet)
   - ESP32 shows "Awaiting admin assignment" on LCD

2. **Admin assignment:**
   - Admin logs into system, sees list of unassigned MAC addresses
   - Admin manually assigns `device_id` (e.g., `esp32-001`) to the MAC
   - Admin can also set tenant/outlet name at this time

3. **ESP32 handshake:**
   - ESP32 calls `POST /api/v1/devices/handshake` with `{ mac_address }`
   - Server returns `{ device_id: "esp32-001", token: "...", api_base: "..." }`
   - ESP32 stores credentials and begins normal operation

4. **Fallback (offline):**
   - If no internet, ESP32 creates AP for staff to configure via `/settings`
   - Staff can manually enter `device_id` and `token`

Local configuration fields to expose in the portal:
- Connectivity:
  - Wi‑Fi SSID/password
  - API base URL (e.g., `https://api.example.com`)
  - Optional proxy settings
- Identity & security:
  - Readonly device fingerprint: MAC, chip ID, firmware version
  - device_id (editable only in manual mode)
  - Bearer token (write‑only, never displayed after save)
  - TLS root CA bundle selection/version
- Operation:
  - Timezone or fixed UTC offset (timestamps are sent in UTC; offset is for local UI only)
  - LCD sleep timeout
  - Treatment durations (override, with min/max guards)
  - Relay polarity (active‑HIGH/LOW)
  - RTC set/sync action (Sync from NTP now)
- Reliability/diagnostics:
  - Queue status: length, oldest event time, last error
  - Test upload button: generate a test event and attempt upload
  - Logs snapshot (recent errors) for copy/paste
- Maintenance:
  - OTA firmware URL/channel (or toggle to enable server‑driven OTA)
  - Reset options: Wi‑Fi only; credentials only; full factory reset

Notes:
- Default `device_id` can be derived from MAC to simplify labeling (e.g., print sticker with same ID). Final `device_id` is confirmed by server during claim and stored in NVS.
- The portal should require the claim code or admin PIN to change identity‑sensitive fields after initial claim.
- For security, treat tokens as write‑only; allow replacing but not reading them back.

### 4.2) Local Staff Web UI (`/settings`)

Purpose: Allow only staff to view diagnostics and change operational settings on‑site without reflashing.

Access:
- AP mode (device creates hotspot): `http://192.168.4.1/settings`
- Station mode (device joined to site Wi‑Fi): `http://<device-ip>/settings`

Authentication:
- Login required (staff‑only). Options:
  - Username/password stored in NVS, rotated by staff.
  - Or one‑time admin PIN derived from token; upon login, issue a session cookie (HttpOnly).
- After provisioning, identity‑sensitive fields require re‑auth (step‑up) before saving.

Features (typical pages):
- Overview:
  - Device fingerprint (MAC, device_id, firmware), Wi‑Fi status, RTC time, queue length, last upload status
- Counters:
  - View current B/S/P counters; buttons to reset all or individual counters with confirmation
  - Monthly rollover info (last_reset_year/month), and a manual “Perform Rollover” action (guarded)
- Connectivity:
  - Change Wi‑Fi SSID/password (device will reconnect on save)
  - API base URL
  - Test upload (send a test event)
- Identity & Security:
  - View device_id (read‑only by default); replace token (write‑only)
  - Enable/disable local AP; change AP SSID/password
- Operation:
  - LCD sleep timeout, relay polarity (active‑HIGH/LOW), treatment durations (with safe bounds)
  - RTC: sync from NTP now, or set time manually
- Maintenance:
  - Check for OTA update, or set OTA URL/channel, reboot, safe factory reset options

Storage & footprint:
- The UI can be served as small static HTML/CSS/JS files from LittleFS/SPIFFS (tens of KB). On a 4MB ESP32 module, this is negligible.
- Alternatively, embed minimal HTML in PROGMEM to avoid filesystem. Trade‑off: harder to update UI without reflashing.

Security notes:
- Prefer serving the UI only on local network/AP and require login. Full HTTPS on embedded local IP is complex; mitigate with strong passwords, short sessions, and rate limiting.
- Protect sensitive operations behind confirmation dialogs and re‑auth.

#### Device ID policy and behavior (mandatory)
- Set via local UI (AP mode) by staff: If `device_id` is not yet set, the `/settings` page allows entering it once. After saving, all JSON events include this `device_id`.
- Non‑erasable: The UI never allows clearing `device_id` to empty/null. Attempts to save blank are rejected.
- Change allowed, not delete: Changing `device_id` is possible only with step‑up admin auth and explicit confirmation. A server side check (optional call to `/api/v1/devices/verify`) can be required before accepting the change.
- Redundant storage: Store `device_id` in NVS with a checksum and a backup copy. On boot, validate checksum; if main is corrupted but backup is valid, restore automatically.
- UI safeguards: Show `device_id` as read‑only after initial set. Enable an “override mode” (admin PIN) to edit. Always require re‑auth to save.
- Event payload: Every API payload includes `device_id` (see schemas above). The device refuses to upload events if `device_id` is missing.

### 4.3) Quick guide: Best (simple) way to set device_id

Use this easy process. Clients do nothing.

Steps:
1) Power the device. It creates a hotspot if no Wi‑Fi is set.
2) Connect your phone/laptop to the device Wi‑Fi (AP): `OZONE-xxxx`.
3) Open `http://192.168.4.1/settings`.
4) Log in with the staff password.
5) Enter the device ID (match the sticker on the unit), then Save.
6) Set the site Wi‑Fi name and password (optional for testing), then Save.
7) Press “Test upload” to confirm it can talk to the server.

Why this is good:
- You control the ID. No internet needed.
- The ID is saved safely and used in every JSON sent to the server.
- The ID cannot be erased by mistake (only changed with admin approval).

Avoid these mistakes:
- Do not leave `device_id` blank.
- Do not reuse an ID from another unit. Each unit must be unique.
- If you change the ID later, tell the backend team so records stay clean.

### 4.4) Device ↔ Server handshake (simple)

What is it?
- A quick check between the device and your server to make sure the device is real, the `device_id` is correct, and the token is valid. Done at boot and sometimes later.

When it runs
- On boot (after Wi‑Fi connects)
- When the token is changed in `/settings`
- If uploads get a 401/403 (token problems)

What the device sends
```json
{
  "device_id": "esp32-001",
  "firmware": "1.0.0",
  "mac": "AA:BB:CC:DD:EE:FF"
}
```
Headers: `Authorization: Bearer <token>`

What the server replies (example)
```json
{
  "ok": true,
  "device_id": "esp32-001",
  "policy": {
    "api_base": "https://api.example.com",
    "tz": "+00:00"
  }
}
```

If handshake is OK
- Device starts (or resumes) sending events normally.
- Stores any updated settings from the server (e.g., API base URL).

If handshake fails
- 401/403: token is wrong/expired. The device pauses uploads, shows an error in `/settings`, and retries later (with backoff). Staff can replace the token.
- 404/not found: `device_id` unknown to server. Device pauses uploads and shows a clear message in `/settings`.
- Network error: keep events queued; keep retrying in the background.

Why this helps
- Stops bad data (wrong ID/token) early.
- Lets the server push simple policy updates.
- Gives staff a clear pass/fail signal in the local UI.

### 4.5) Backend integration checklist (what the server must provide)

Minimum APIs
- Device registration: `POST /api/v1/devices/register`
  - Request: `{ mac_address, firmware_version }`
  - Response: `{ status: "pending_assignment" }` (first time) or `{ status: "assigned", device_id }`
- Auth: Bearer token validation for all endpoints.
- Handshake: `POST /api/v1/devices/handshake`
  - Request: `{ mac_address }`
  - Response: `{ device_id, token, policy: { api_base, tz } }`
  - Errors: 404 if MAC not found or not assigned
- Events: `POST /api/v1/ozone/events`
  - Idempotent by `event_id` (return `{ack:true}` for duplicates).
  - Validate pairing: `device_id` must belong to `mac` in registry.

Device registry
- Store: `{ device_id, mac_sta, status, tenant/outlet, created_at, assigned_at }`.
- Status values: `pending_assignment`, `assigned`, `active`, `inactive`
- Enforce uniqueness of `device_id` and `mac_sta`.
- Map device → outlet/site (your friendly names live here).
- Admin UI: List unassigned MACs, assign device_id, set tenant names.

Idempotency
- Persist incoming events keyed by `event_id`.
- On duplicates: return HTTP 200 `{ack:true, event_id}` without double‑counting.

Token management
- Issue/rotate bearer tokens per device.
- Blacklist/revoke tokens to disable devices.

Security
- HTTPS (TLS) with a trusted CA.
- Rate limiting and basic abuse protections per device.

Observability
- Logs/metrics for handshake results, event ingest rate, dedupe hits, errors.
- Admin UI or API to see device status, last seen, queue depth (if reported).

Time & policy
- Accept and store timestamps in UTC.
- Optionally return simple policy values in handshake (e.g., `api_base`, time offset for UI).

### 5) Configuration toggles (future)
- Adjustable treatment durations via config (with a safe min/max).
- Configurable LCD sleep timeout.
- Enable/disable cloud logging.
- Admin combo to print diagnostics to serial (I2C addresses, button states, RTC time).

### 6) At-least-once delivery guarantee (device → server)

Goal: Never lose a treatment start event. If there are 9,999 starts, the server must store 9,999 distinct events. Device ensures at-least-once delivery; server deduplicates for effective exactly-once processing.

- Persistent event queue on device (LittleFS or SPIFFS):
  - On button press (BASIC/STANDARD/PREMIUM):
    - Increment local counter (already implemented)
    - Create an event record with fields:
      - `device_id` (stable per board)
      - `firmware` (semantic version)
      - `event_id` (monotonic counter per device or UUID; include `device_id` prefix)
      - `event` = `treatment`
      - `treatment` = `BASIC` | `STANDARD` | `PREMIUM`
      - `counter` (post-increment value)
      - `ts` (RTC or NTP ISO8601)
    - Append to an append-only queue file (e.g., newline JSON lines) in flash

- Background uploader (oldest-first):
  - Triggers on: new event appended, Wi‑Fi connect, boot
  - POST to `/api/v1/ozone/events` with JSON body (see examples above)
  - Timeouts: connect 3s, total 10s; retries with exponential backoff up to 5 min, ±20% jitter
  - Success criteria: HTTP 200 with `{ "ack": true, "event_id": "..." }`
  - Only then remove the event from the queue. Otherwise, keep and retry later

- Power-loss safety:
  - Queue is on flash; on reboot, resume upload from the oldest unacked event
  - Periodic compaction when queue is drained or exceeds size thresholds

- Network/Server behavior:
  - Use HTTPS and bearer token auth
  - Server must be idempotent by `event_id`:
    - If event already stored, return `{ack:true}` again (dedupe)
  - Optional: 409 with idempotency semantics acceptable if client treats it as ack

- Visibility & monitoring:
  - Maintain and expose (serial or API) queue length, last upload status, last error
  - Optional: local error LED blink pattern for prolonged offline conditions

- Storage pressure & retention:
  - Soft cap queue file (e.g., 1–4 MB). If capacity pressure occurs, raise alert via serial/LED; do not drop events
  - Consider splitting by day (events-YYYYMMDD.q) to simplify retention and compaction

- Device identity & clock:
  - `device_id` provisioned at manufacture/first boot (stored in NVS/EEPROM)
  - RTC (DS3231) preferred; fallback NTP sync if available; include `ts` in UTC

#### Decision: Option A (Delete-on-ack queue) — Selected
- We will implement the durable delivery queue only. Events are stored on flash until the server acknowledges them, then removed immediately. The server is the system of record and audit store.
- We will not retain a separate on-device audit log beyond what’s required for delivery. This minimizes flash usage and complexity while still guaranteeing 100% delivery.

---

## Known Considerations (for future work)

- Counter type & growth: Prefer `uint32_t` (0..4,294,967,295) for counters to avoid overflow. Use `uint64_t` only if you truly expect more than 4.29B treatments per category.
- Relay polarity & power: Verify relay boards (active-HIGH vs active-LOW). Ensure 5V supply headroom; shared GND with ESP32; flyback protection present.
- Business rule: Counter increments at start, even if immediately stopped (2s hold). Confirm this is desired billing behavior.
- Identity & security: Provision persistent `device_id`, secure API token storage, use HTTPS with root CA stored in flash, plan rotation.
- Delivery queue implementation: Append-only LittleFS records; oldest-first uploads; delete only on server ack; exponential backoff with jitter; resume on boot; server dedupe by `event_id`.

---

## Monthly Counter Rollover (RTC‑based, deferred)

Goal: Reset the on-device monthly counters at the start of each month (00:00 on the 1st) even if the machine is powered off at that moment. Server remains the source of truth for billing via events; device reset is for on-site UX/accounting.

Design (no code yet):
- Persist in NVS/EEPROM:
  - `last_reset_year`, `last_reset_month`
  - `current_month_counters` (B/S/P) — what the LCD shows
  - `lifetime_counters` (B/S/P) — never reset (optional but recommended)
  - `last_month_archive` with (B/S/P, year, month) — optional local reference
- On boot or first loop tick (and not during an active treatment):
  1) Read RTC date/time (UTC recommended to avoid DST issues).
  2) If `(rtc_year, rtc_month) != (last_reset_year, last_reset_month)`, perform rollover:
     - Archive `current_month_counters` with old `(year, month)` to `last_month_archive` (optional)
     - Add `current_month_counters` into `lifetime_counters` (optional)
     - Zero `current_month_counters`
     - Set `last_reset_year/month = rtc_year/month`
     - Commit atomically to storage
- If powered off on the 1st: reset happens at next power‑up/wake before any new treatments start.
- If multiple months were missed: loop the rollover until `last_reset_month` catches up to RTC month (archive zeros if needed).
- Do not reset while a treatment is running; check and reset before allowing a new start.

Notes:
- Use RTC as time source; store/compute in UTC. If local midnight is required, convert once using a fixed offset or server policy.
- Server will compute official monthly totals from delivered events (at‑least‑once queue). Device monthly reset is convenience for on-site operations.

## Backend API (Postman)
See `backend/README.md` for full, copy-paste Postman bodies.

Key endpoints (local dev):
- Handshake (get token):
  - POST `http://localhost:8000/api/handshake/`
  - Body:
```
{
  "mac": "EC:E3:34:46:2B:C0",
  "firmware": "1.0.0"
}
```
- Ingest event (Bearer <token>):
  - POST `http://localhost:8000/api/events/`
  - Body:
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
- List events: GET `http://localhost:8000/api/events/?device_id=esp32-001&exclude_status=true`
- Device status online: GET `http://localhost:8000/api/devices/online/`

