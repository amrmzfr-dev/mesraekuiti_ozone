================================================================================================================================================================
========================================================= OZONE MACHINE COUNTER SYSTEM (ESP32)===================================================
================================================================================================================================================================

This firmware powers an ozone machine counter-and-control panel built on an ESP32. It manages three treatment types (BASIC, STANDARD, PREMIUM) with per‑treatment timers, relays, and persistent counters stored in EEPROM. Event/command queues are persisted on an SD card for large, durable storage. The system is designed to be robust for rental/production scenarios with button-driven operation.

### Key Features
- Three treatments:
  - BASIC (B)
  - STANDARD (S)
  - PREMIUM (P)
- Treatment timers: 5 min, 10 min, 15 min (B/S/P)
- **6-channel relay system**: 3 treatment relays + 3 LED mirror relays
- **Individual relay control**: Each treatment activates its specific relay + LED
- Per‑treatment counters persisted in EEPROM (survive power cycles)
- Start‑on‑press counting (counter increments immediately on button press, not at timer end)
- Long‑press stop during a running timer (PREMIUM button ≥ 2s)
- Wi‑Fi connectivity with local web configuration interface
- AP mode fallback for initial setup and configuration
- Cloud logging API with persistent SD card queueing and exponential backoff retry
- **Automatic WiFi reconnection** with smart retry logic and connection quality monitoring

===============================================================================================================================================================
============================================================================ HARDWARE =========================================================================
===============================================================================================================================================================

### Controller
- Board: ESP32 DevKit (esp32dev)

### Buttons
- Module type: 2‑pin buttons to GND, with internal pull‑ups enabled
- Pins (direct actions):
  - BASIC: GPIO 27
  - STANDARD: GPIO 14
  - PREMIUM: GPIO 15

Important: Avoid ESP32 bootstrap pins (e.g., GPIO0, GPIO2) for buttons due to boot mode interference and phantom presses.

### Relay / Output
- **8-channel relay board** (6 channels used, 2 reserved)
- **Treatment Relays** (3 channels for ozone generator control):
  - BASIC Treatment: GPIO 23 (IN1)
  - STANDARD Treatment: GPIO 22 (IN2)
  - PREMIUM Treatment: GPIO 21 (IN3)
- **LED Mirror Relays** (3 channels for LED indication):
  - BASIC LED: GPIO 19 (IN4)
  - STANDARD LED: GPIO 18 (IN5)
  - PREMIUM LED: GPIO 5 (IN6)
- **Reserved Channels** (2 channels for future expansion):
  - IN7: Available for future use
  - IN8: Available for future use
- Ensure relay board GND is common with the ESP32
- Each treatment activates its specific relay + corresponding LED mirror

### RTC (optional, recommended)
- Module: DS3231 (I2C)
- Pins (second I2C bus):
  - SDA: GPIO 25 (Wire1 SDA)
  - SCL: GPIO 26 (Wire1 SCL)
- Address: 0x68

### Power
### SD Card (recommended for persistence)
- Module: microSD card SPI adapter
- Pins (SPI):
  - CS: GPIO 33
  - SCK: GPIO 32
  - MOSI: GPIO 13
  - MISO: GPIO 35
- Power: 3.3V or 5V (per adapter), common GND with ESP32
- Notes: SD card holds event and command queues as JSONL files
- ESP32 is powered via USB or regulated 5V input. Ensure sufficient current budget.

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
  - `EEPROM@2.0.0`
  - `bblanchon/ArduinoJson@^7.0.4`
  - `SD@^2.0.0`
  - `monitor_speed = 115200`

### Source Structure
- **Main file**: `src/main.cpp` — Core system + pins + buttons + timers + relays + EEPROM + SD card + Wi‑Fi
- **Pins**: `include/pins.h` — Centralized pin map and constants
- (Removed) `src/config.h`, `src/web_interface.h/.cpp` — no longer used

### Pin Map (code)
```
BUTTONS: BASIC=27, STANDARD=14, PREMIUM=15
TREATMENT RELAYS: BASIC=23(IN1), STANDARD=22(IN2), PREMIUM=21(IN3)
LED MIRROR RELAYS: BASIC=19(IN4), STANDARD=18(IN5), PREMIUM=5(IN6)
RTC: SDA=25, SCL=26
RESERVED: IN7, IN8 (available for future expansion)
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
====================================================================== WI‑FI RECONNECTION =====================================================================
===============================================================================================================================================================

### Automatic WiFi Reconnection
The system includes robust WiFi reconnection capabilities to ensure continuous operation during network outages.

**Reconnection Features:**
- **Periodic Reconnection**: Automatic attempts every 30 seconds when disconnected
- **Event-Driven Triggers**: Immediate reconnection on network operation failures
- **Exponential Backoff**: Smart retry intervals (30s → 60s → 120s → 300s max)
- **Connection Quality Monitoring**: RSSI tracking with degradation warnings
- **Jitter**: ±20% randomization to prevent network flooding

**Reconnection Triggers:**
- Handshake failures during device registration
- Upload failures during event transmission
- Command polling failures during remote command retrieval
- Periodic checks when offline

**Connection Quality Thresholds:**
- **Good Signal**: RSSI > -70 dBm
- **Degraded Signal**: RSSI -80 to -70 dBm (warning issued)
- **Poor Signal**: RSSI < -80 dBm (reconnection may be triggered)
- **Critical Signal**: RSSI < -90 dBm (connection unstable warning)

**Debug Commands:**
- `m` - Force immediate reconnection attempt
- `w` - Display WiFi diagnostics and signal strength
- `t` - Test network connectivity

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
- **Local Storage (SD card)**: JSONL queues
  - Events: `events.jsonl` (default max ~4MB)
  - Commands: `commands.jsonl` (default max ~1MB)
- **Reliability**: At-least-once delivery with automatic retry and deduplication
- Handshake mechanism: Automatic device registration and token retrieval
- Clock & timestamps: RTC (DS3231) preferred; falls back to NTP/RTC
- Security: HTTPS with Bearer token authentication

**Production Features:**
- Events queued locally during network outages (to SD card)
- Exponential backoff with ±20% jitter
- Queue persistence across power cycles (SD card)
- Background processing loop
- Server acknowledgment required before event deletion

**Backend API Endpoints:**
- Handshake (get token): POST `/api/handshake/`
- Ingest event: POST `/api/events/`
- List events: GET `/api/events/?device_id=esp32-001&exclude_status=true`
- Device status: GET `/api/devices/online/`

===============================================================================================================================================================
========================================================================== UI & BEHAVIOR ======================================================================
===============================================================================================================================================================

### Main Operation
- Button-driven operation with three treatment modes
- Counters in the format `0000 0000 0000` (B S P)
- Labels ` B   S   P ` (buttons are direct action)
- Treatment types: `BASIC  STD  PREM`

Navigation (direct-start buttons):
- BASIC button (GPIO27): starts BASIC timer immediately
- STANDARD button (GPIO14): starts STANDARD timer immediately
- PREMIUM button (GPIO15): starts PREMIUM timer immediately

Counting rule (business logic):
- The counter increments immediately when button starts a treatment.
- The counter does not increment again when the timer completes.

### Timer Operation
- Treatment name display:
  - BASIC TREATMENT
  - STANDARD TREATMENT
  - PREMIUM TREATMENT
- `MM:SS` countdown timer
- Stop instruction: "hold x for 2s to stop"

While timer is active:
- All start buttons are ignored.
- PREMIUM button long‑press (≥ 2s) stops the timer and returns to main operation.

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

Counters are stored in ESP32 EEPROM emulation and auto‑loaded on boot. Large/log data lives on SD card.

Layout:
- Address 0..3:  B counter (uint32_t)
- Address 4..7:  S counter (uint32_t)
- Address 8..11: P counter (uint32_t)
- Address 12..13: Magic number 0x1234 for data validity

When counters change (start of a treatment or after reset), values are saved immediately via `EEPROM.commit()`.

### SD Card Persistence
- Files:
  - `events.jsonl`: one JSON object per line for treatment events
  - `commands.jsonl`: one JSON object per line for pending commands/results
- Initialization: SD is mounted in `setup()`; card type/size printed to serial
- Behavior:
  - On enqueue: append a line to the corresponding file
  - On upload success: remove the first line (oldest) and rewrite remainder
  - Size caps: events ~4MB, commands ~1MB (configurable in code)
- Failure handling:
  - If SD init fails, firmware logs the error and continues (counters remain in EEPROM)
  - Queues resume on next boot; nothing is lost between power cycles

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
- LCD functionality has been removed from this firmware.
- System operates as a headless device with button-driven operation.

Buttons not detected / phantom presses:
- Ensure INPUT_PULLUP is used and buttons go to GND
- Avoid boot‑strap pins (GPIO0, GPIO2)
- Verify button functionality through web interface or debugging

Relays not switching:
- Ensure a common GND between relay module and ESP32
- Confirm relay board logic level compatibility and INx mapping

WiFi connection issues:
- System automatically attempts reconnection every 30 seconds
- Use debug command `m` to force immediate reconnection
- Check signal strength with `w` command
- Monitor RSSI levels for connection quality

===============================================================================================================================================================
====================================================================== CODE STRUCTURE (HIGH LEVEL) ============================================================
===============================================================================================================================================================

- `setup()`
  - Init buttons, relays
  - Init EEPROM and load counters
  - Initialize main operation state

- `loop()`
  - `handleButtons()` for navigation, start/stop, reset flow
  - `updateTimer()` if timer active
  - Periodic system updates (only when needed)

- Display
  - `updateDisplay()` manages main or timer states
  - `updateTimerDisplay()` handles timer countdown logic

- Actions
  - `startTimer()` sets duration, activates relay, increments and saves counter
  - `stopTreatment()` stops timer and deactivates relays
  - `resetAllCounters()` zeros counters and saves to EEPROM

- Persistence
  - `saveCountersToEEPROM()` / `loadCountersFromEEPROM()` with magic number validation

===============================================================================================================================================================
========================================================================== OPERATIONAL NOTES ==================================================================
===============================================================================================================================================================

- Counters increment at treatment start (button press), not on completion. This is intentional for billing integrity in rental scenarios.
- Navigation (UP/DOWN) is disabled during an active timer.
- PREMIUM long‑press (≥ 2s) only stops an active timer; it does nothing on the main page except starting a treatment with a short press.
- Reset requires two steps: 10s UP+DOWN hold, then SELECT to confirm (or DOWN to cancel).

===============================================================================================================================================================
============================================================================ CUSTOMIZATION ====================================================================
===============================================================================================================================================================

- Change button pins if your board differs; avoid GPIO0/GPIO2.
- Modify relay polarity if your hardware uses active‑LOW modules.

===============================================================================================================================================================
========================================================================== LICENSE & CREDITS ==================================================================
===============================================================================================================================================================

- Uses Arduino EEPROM emulation libraries.
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
- Delivery queue implementation: Append-only SD card JSONL records; oldest-first uploads; delete only on server ack; exponential backoff with jitter; resume on boot; server dedupe by `event_id`.

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

