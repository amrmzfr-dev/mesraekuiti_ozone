================================================================================================================================================================
========================================================= OZONE MACHINE COUNTER SYSTEM (ESP32 + 20x4 I2C LCD)===================================================
================================================================================================================================================================

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
- Cloud logging API with persistent queueing and exponential backoff retry

===============================================================================================================================================================
============================================================================ HARDWARE =========================================================================
===============================================================================================================================================================

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
- Pins (direct actions):
  - BASIC: GPIO 27
  - STANDARD: GPIO 14
  - PREMIUM: GPIO 15

Important: Avoid ESP32 bootstrap pins (e.g., GPIO0, GPIO2) for buttons due to boot mode interference and phantom presses.

### Relay / Output
- Single relay channel (active level configurable in code, default active‑LOW boards are supported)
- Relay IN → GPIO 23 (shared for all BASIC/STANDARD/PREMIUM treatments)
- Ensure relay board GND is common with the ESP32

Note: A 4‑channel relay board can be used but only IN1 is wired; other channels remain unconnected.

### RTC (optional, recommended)
- Module: DS3231 (I2C)
- Pins (second I2C bus):
  - SDA: GPIO 25 (Wire1 SDA)
  - SCL: GPIO 26 (Wire1 SCL)
- Address: 0x68

### Power
- The LCD and relays are powered from 5V; ESP32 is powered via USB or regulated 5V input. Ensure sufficient current budget.

### Wi‑Fi
- ESP32 has built‑in Wi‑Fi capability
- Default AP mode: SSID `OZONE-CONFIG`, Password `mb95z78y`
- Default client mode: SSID `testtest`, Password `mb95z78y`
- Web interface accessible at `http://192.168.4.1` (AP mode) or device IP (client mode)

===============================================================================================================================================================
============================================================================ SOFTWARE =========================================================================
===============================================================================================================================================================

### Project
- PlatformIO (Arduino framework)
- `platformio.ini` includes:
  - `LiquidCrystal_I2C@^1.1.4`
  - `jm_PCF8574@^2.0.0` (kept in deps; current code uses `LiquidCrystal_I2C`)
  - `EEPROM@2.0.0`
  - `bblanchon/ArduinoJson@^7.0.4`
  - `monitor_speed = 115200`

### Source Structure
- **Main file**: `src/main.cpp` — Core system + pins + LCD + buttons + timers + relays + EEPROM + Wi‑Fi + embedded web UI
- **Pins**: `include/pins.h` — Centralized pin map and constants
- (Removed) `src/config.h`, `src/web_interface.h/.cpp` — no longer used

### Pin Map (code)
```
SDA=21, SCL=22
UP=27, DOWN=14, SELECT=15
RELAY=23
RTC_SDA=25, RTC_SCL=26
```

===============================================================================================================================================================
=================================================================== CODE ARCHITECTURE =========================================================================
===============================================================================================================================================================

### Multitasking Architecture (FreeRTOS on ESP32)
The firmware is organized as several cooperative tasks for responsiveness:

Tasks (and priorities):
- TaskInput (prio 4, APP core):
  - Debounced button reads (B/S/P)
  - PREMIUM long‑press stop detection
  - Sends ControlMsg to control queue
- TaskControl (prio 3, APP core):
  - Starts/stops treatments, updates timers/relay
  - Enqueues NetEvent to network queue when treatment starts
  - Manages LCD backlight sleep
- TaskDisplay (prio 2, APP core):
  - Refreshes LCD only when dirty at a steady cadence
- TaskNet (prio 1, PRO core):
  - Runs local web server
  - Uploads treatment events (handshake on demand)

Queues:
- controlQueue: ControlMsg (from input → control)
- netQueue: NetEvent (from control → network uploader)

Files:
- `src/main.cpp`: all logic (tasks, peripherals, web UI, backend)
- `include/pins.h`: centralized pins and pin map

### Benefits of Simple Structure
- **Simplicity**: Easy to understand and navigate
- **Maintainability**: All core functionality in one place
- **Readability**: Clear separation between core logic and web interface
- **Efficiency**: No unnecessary abstraction overhead
- **Debugging**: Easy to trace through the main flow

===============================================================================================================================================================
====================================================================== WI‑FI CONFIGURATION ====================================================================
===============================================================================================================================================================

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

===============================================================================================================================================================
====================================================================== CLOUD LOGGING API ======================================================================
===============================================================================================================================================================

### Cloud Logging for Treatment Events
The system reports treatment button presses to a web backend for billing/auditing purposes.

**Event Reporting:**
- `treatment` events sent immediately on button press (includes B/S/P, counter value after increment, timestamp)
- No completion events needed - only treatment initiation is tracked

**HTTP Interface:**
- POST `/api/events/`
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

**Current Implementation:**
- Event identity (idempotency key): Monotonic per-device sequence combined with device ID
- Device identity: Persistent `device_id` and `token` stored in EEPROM
- **Queueing & Retry**: Persistent event queue with exponential backoff retry (2s → 5min)
- **Local Storage**: LittleFS-based JSONL queue with 4MB size limit
- **Reliability**: At-least-once delivery with automatic retry and deduplication
- Handshake mechanism: Automatic device registration and token retrieval
- Clock & timestamps: RTC (DS3231) preferred, UTC ISO-8601 format
- Security: HTTPS with Bearer token authentication

**Production Features:**
- Events queued locally during network outages
- Exponential backoff with ±20% jitter
- Queue persistence across power cycles
- Background TaskNet processing
- Server acknowledgment required before event deletion

**Backend API Endpoints:**
- Handshake (get token): POST `/api/handshake/`
- Ingest event: POST `/api/events/`
- List events: GET `/api/events/?device_id=esp32-001&exclude_status=true`
- Device status: GET `/api/devices/online/`

===============================================================================================================================================================
========================================================================== UI & BEHAVIOR ======================================================================
===============================================================================================================================================================

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

===============================================================================================================================================================
=========================================================================== TIMERS ============================================================================
===============================================================================================================================================================

Current timings (Testing; milliseconds):
- BASIC: 5,000 ms (5 s)
- STANDARD: 10,000 ms (10 s)
- PREMIUM: 15,000 ms (15 s)

Note: Production values are 5/10/15 minutes. Switch back before deployment.

===============================================================================================================================================================
====================================================================== EEPROM PERSISTENCE =====================================================================
===============================================================================================================================================================

Counters are stored in ESP32 EEPROM emulation and auto‑loaded on boot.

Layout:
- Address 0..3:  B counter (uint32_t)
- Address 4..7:  S counter (uint32_t)
- Address 8..11: P counter (uint32_t)
- Address 12..13: Magic number 0x1234 for data validity

When counters change (start of a treatment or after reset), values are saved immediately via `EEPROM.commit()`.

===============================================================================================================================================================
======================================================================== BUILD & UPLOAD =======================================================================
===============================================================================================================================================================

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

===============================================================================================================================================================
======================================================================== TROUBLESHOOTING ======================================================================
===============================================================================================================================================================

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

===============================================================================================================================================================
============================================================================ LCD SLEEP ========================================================================
===============================================================================================================================================================

- The LCD backlight turns off after 2 minutes of inactivity on the main page.
- Any button press wakes the screen. The wake press does not navigate or start a treatment.
- The LCD never sleeps while a treatment timer is active.

===============================================================================================================================================================
====================================================================== CODE STRUCTURE (HIGH LEVEL) ============================================================
===============================================================================================================================================================

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
  - `stopTreatment()` stops timer and deactivates relays
  - `resetAllCounters()` zeros counters and saves to EEPROM

- Persistence
  - `saveCountersToEEPROM()` / `loadCountersFromEEPROM()` with magic number validation

===============================================================================================================================================================
========================================================================== OPERATIONAL NOTES ==================================================================
===============================================================================================================================================================

- Counters increment at treatment start (SELECT press), not on completion. This is intentional for billing integrity in rental scenarios.
- Navigation (UP/DOWN) is disabled during an active timer.
- SELECT long‑press (≥ 2s) only stops an active timer; it does nothing on the main page except starting a treatment with a short press.
- Reset requires two steps: 10s UP+DOWN hold, then SELECT to confirm (or DOWN to cancel).

===============================================================================================================================================================
============================================================================ CUSTOMIZATION ====================================================================
===============================================================================================================================================================

- Change button pins if your board differs; avoid GPIO0/GPIO2.
- Adjust LCD centering by altering `lcd.setCursor(col,row)` in `updateDisplay()`.
- Modify relay polarity if your hardware uses active‑LOW modules.

===============================================================================================================================================================
========================================================================== LICENSE & CREDITS ==================================================================
===============================================================================================================================================================

- Uses `LiquidCrystal_I2C`, `jm_PCF8574`, and Arduino EEPROM emulation libraries.
- Project intended for embedded control/rental system use cases.


===============================================================================================================================================================
========================================================================= NEXT PLAN / PROPOSED ================================================================
===============================================================================================================================================================

### OTA (Over-The-Air) Update Functionality
- Goal: Enable remote firmware updates without physical access to the device
- Proposed features:
  - Secure OTA update mechanism using ESP32's built-in OTA capabilities
  - Update server endpoint for firmware distribution
  - Rollback capability in case of failed updates
  - Update verification and integrity checking
  - Progress reporting during update process
  - Automatic restart after successful update

- Implementation approach:
  - Use ESP32's `Update` library for OTA functionality
  - Implement update server with authentication
  - Add firmware version checking and comparison
  - Store update status and progress in EEPROM/NVS
  - Web interface for manual update triggers
  - Automatic update checks on boot and periodic intervals

===============================================================================================================================================================
=============================================================== KNOWN CONSIDERATIONS (FUTURE WORK) ============================================================
===============================================================================================================================================================

- Counter type & growth: Prefer `uint32_t` (0..4,294,967,295) for counters to avoid overflow. Use `uint64_t` only if you truly expect more than 4.29B treatments per category.
- Relay polarity & power: Verify relay boards (active-HIGH vs active-LOW). Ensure 5V supply headroom; shared GND with ESP32; flyback protection present.
- Business rule: Counter increments at start, even if immediately stopped (2s hold). Confirm this is desired billing behavior.
- Identity & security: Provision persistent `device_id`, secure API token storage, use HTTPS with root CA stored in flash, plan rotation.
- Delivery queue implementation: Append-only LittleFS records; oldest-first uploads; delete only on server ack; exponential backoff with jitter; resume on boot; server dedupe by `event_id`.

===============================================================================================================================================================
========================================================= MONTHLY COUNTER ROLLOVER (RTC‑BASED, DEFERRED) ======================================================
===============================================================================================================================================================

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

===============================================================================================================================================================
======================================================================== BACKEND API (POSTMAN) ================================================================
===============================================================================================================================================================

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

