# Ozone Machine System Flow Documentation

## Overview
This document provides a comprehensive flow analysis of the ozone machine firmware system. The system is designed to operate three treatment modes (Basic, Standard, Premium) with network connectivity for remote monitoring and command execution.

## System Architecture

### Hardware Components
- **ESP32 Microcontroller**: Main processing unit
- **Buttons**: 3 physical buttons for treatment selection
  - BASIC (Pin 27)
  - STANDARD (Pin 14) 
  - PREMIUM (Pin 15)
- **Relays**: 8-channel relay board (6 channels used, 2 reserved)
  - **Treatment Relays**: 3 channels for ozone generator control
    - BASIC Treatment (Pin 23, IN1)
    - STANDARD Treatment (Pin 22, IN2)
    - PREMIUM Treatment (Pin 21, IN3)
  - **LED Mirror Relays**: 3 channels for LED indication
    - BASIC LED (Pin 19, IN4)
    - STANDARD LED (Pin 18, IN5)
    - PREMIUM LED (Pin 5, IN6)
  - **Reserved Channels**: 2 channels for future expansion
    - IN7: Available for future use
    - IN8: Available for future use
- **RTC**: DS3231 Real-Time Clock for timestamp accuracy
- **WiFi**: Dual mode (AP + STA) for configuration and connectivity

### 8-Channel Relay Board Wiring Diagram
```
ESP32 GPIO → 8-Channel Relay Board
GPIO 23 → IN1 (BASIC Treatment)
GPIO 22 → IN2 (STANDARD Treatment)  
GPIO 21 → IN3 (PREMIUM Treatment)
GPIO 19 → IN4 (BASIC LED)
GPIO 18 → IN5 (STANDARD LED)
GPIO 5  → IN6 (PREMIUM LED)
        → IN7 (Reserved)
        → IN8 (Reserved)

Common GND connection required between ESP32 and relay board
```

### Software Components
- **Arduino Framework**: Base development platform
- **LittleFS**: File system for event/command queuing
- **EEPROM**: Persistent storage for counters and credentials
- **ArduinoJson**: JSON parsing and generation
- **WiFiClientSecure**: HTTPS communication
- **RTClib**: Real-time clock management

## System Flow Diagrams

### 1. Initialization Phase (setup())

```
Power On
    ↓
Serial Communication Start (115200 baud)
    ↓
EEPROM Initialization & Load Data:
    - Load counters (B/S/P)
    - Load WiFi credentials
    - Load device identity
    ↓
Increment Reset Counter (for unique event IDs)
    ↓
LittleFS Storage Setup:
    - Initialize event queue
    - Initialize command queue
    ↓
GPIO Pin Configuration:
    - BUTTON_BASIC_PIN (27) → INPUT_PULLUP
    - BUTTON_STANDARD_PIN (14) → INPUT_PULLUP  
    - BUTTON_PREMIUM_PIN (15) → INPUT_PULLUP
    - RELAY_PIN (23) → OUTPUT (OFF)
    ↓
RTC (Real-Time Clock) Setup
    ↓
WiFi Configuration:
    - Start AP mode ("OZONE-CONFIG")
    - Connect to STA mode (stored credentials)
    ↓
NTP Time Sync (Kuala Lumpur timezone)
    ↓
Device Handshake (if needed):
    - Send MAC address + firmware version
    - Receive device_id + token
    ↓
Initialize Main Operation State
```

### 2. Main Operation Loop (loop())

```
┌─────────────────────────────────────────────────────────────┐
│                    MAIN LOOP (20Hz)                         │
└─────────────────────────────────────────────────────────────┘
                                ↓
                    ┌─────────────────────────┐
                    │     BUTTON PROCESSING    │
                    └─────────────────────────┘
                                ↓
    ┌─────────────────────────────────────────────────────────┐
    │ Button States:                                          │
    │ • BASIC (Pin 27) → Start Basic Treatment (5s)          │
    │ • STANDARD (Pin 14) → Start Standard Treatment (10s)   │
    │ • PREMIUM (Pin 15) → Start Premium Treatment (15s)     │
    │ • PREMIUM Hold (2s) → Stop Current Treatment           │
    └─────────────────────────────────────────────────────────┘
                                ↓
                    ┌─────────────────────────┐
                    │   TREATMENT TIMER      │
                    └─────────────────────────┘
                                ↓
    ┌─────────────────────────────────────────────────────────┐
    │ If Treatment Active:                                    │
    │ • Check elapsed time vs duration                        │
    │ • Auto-stop when duration reached                       │
    │ • Update system state every second                      │
    │ • Relay ON during treatment                             │
    └─────────────────────────────────────────────────────────┘
                                ↓
                    ┌─────────────────────────┐
                    │   NETWORK OPERATIONS   │
                    └─────────────────────────┘
                                ↓
    ┌─────────────────────────────────────────────────────────┐
    │ If WiFi Connected:                                      │
    │                                                         │
    │ 1. COMMAND PROCESSING (Priority):                      │
    │    • Process command queue                              │
    │    • Poll for new commands (every 30s)                 │
    │    • Execute commands (reset, clear, reboot, etc.)     │
    │                                                         │
    │ 2. EVENT UPLOAD:                                        │
    │    • Read next event from queue                         │
    │    • Upload to backend via HTTPS                       │
    │    • Remove from queue on success                      │
    │    • Retry with exponential backoff on failure         │
    │                                                         │
    │ 3. HANDSHAKE (if needed):                              │
    │    • Re-register device if credentials missing         │
    └─────────────────────────────────────────────────────────┘
                                ↓
                    ┌─────────────────────────┐
                    │   OFFLINE OPERATIONS    │
                    └─────────────────────────┘
                                ↓
    ┌─────────────────────────────────────────────────────────┐
    │ If WiFi Disconnected:                                  │
    │ • Show queue status every 10s                          │
    │ • Continue local operations                             │
    │ • Queue events for later upload                         │
    └─────────────────────────────────────────────────────────┘
                                ↓
                    ┌─────────────────────────┐
                    │     50ms DELAY          │
                    └─────────────────────────┘
                                ↓
                            LOOP REPEAT
```

### 3. Treatment Process Flow

```
User Presses Button
        ↓
┌─────────────────────────────────────────┐
│ Check Current State:                    │
│ • If treatment already active → ignore  │
│ • If no treatment → start new one       │
└─────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────┐
│ Treatment Type Selection:               │
│ • BASIC (5min) → counterB++               │
│ • STANDARD (10min) → counterS++           │
│ • PREMIUM (15min) → counterP++            │
└─────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────┐
│ Create Event Record:                    │
│ • Generate unique event_id               │
│ • Record treatment type & counter       │
│ • Add timestamp (RTC/NTP)               │
│ • Queue for upload                      │
└─────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────┐
│ Physical Actions:                       │
│ • Activate specific treatment relay     │
│ • Activate corresponding LED mirror    │
│ • Start timer                            │
│ • Update system state                    │
│ • Save counters to EEPROM               │
└─────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────┐
│ Timer Monitoring:                       │
│ • Check elapsed time every loop         │
│ • Update system state every second      │
│ • Auto-stop when duration reached       │
└─────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────┐
│ Treatment Complete:                     │
│ • Turn OFF all treatment relays         │
│ • Turn OFF all LED mirror relays        │
│ • Reset active state                     │
│ • Return to main operation state        │
└─────────────────────────────────────────┘
```

### 4. Network Communication Flow

```
┌─────────────────────────────────────────┐
│           COMMAND SYSTEM                │
└─────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────┐
│ Poll Commands (every 30s):              │
│ • GET /api/device/{id}/commands/        │
│ • Parse JSON response                    │
│ • Queue commands for execution          │
└─────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────┐
│ Execute Commands:                        │
│ • RESET_COUNTERS → Clear B/S/P counters  │
│ • CLEAR_MEMORY → Clear EEPROM            │
│ • CLEAR_QUEUE → Clear file queues       │
│ • REBOOT_DEVICE → Restart ESP32          │
│ • GET_STATUS → Return current state      │
│ • SYNC_TIME → Acknowledge time sync     │
│ • UPDATE_SETTINGS → Acknowledge         │
│ • UPDATE_FIRMWARE → Not supported       │
└─────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────┐
│ Report Results:                          │
│ • POST /api/device/{id}/commands/{cmd}/ │
│ • Send success/failure status           │
│ • Include current counter values        │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│           EVENT UPLOAD                  │
└─────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────┐
│ Process Event Queue:                    │
│ • Read next event from LittleFS         │
│ • Parse JSON event data                 │
│ • Upload via HTTPS POST                 │
└─────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────┐
│ Upload Success:                         │
│ • Remove event from queue               │
│ • Reset retry delay                     │
│ • Continue with next event              │
└─────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────┐
│ Upload Failure:                         │
│ • Keep event in queue                   │
│ • Apply exponential backoff             │
│ • Retry later                           │
└─────────────────────────────────────────┘
```

## Data Structures

### EEPROM Layout
```
Address Range    | Size | Description
-----------------|------|------------
0-3             | 4B   | counterB (Basic count)
4-7             | 4B   | counterS (Standard count)
8-11            | 4B   | counterP (Premium count)
12-15           | 4B   | Magic value (0x1234)
16-19           | 4B   | resetCounter
20-51           | 32B  | WiFi SSID
60-123          | 64B  | WiFi Password
140-203         | 64B  | Device ID
204-331         | 128B | Device Token
```

### LittleFS Files
```
File Path           | Max Size | Description
--------------------|----------|------------
/events.jsonl       | 4MB     | Treatment events queue
/commands.jsonl     | 1MB     | Remote commands queue
```

### Event JSON Structure
```json
{
  "device_id": "esp32-sim",
  "firmware": "1.0.0-sim",
  "event_id": "device-B0011234567890123456",
  "event": "treatment",
  "treatment": "BASIC",
  "counter": 1,
  "ts": "2025-01-15 14:30:25",
  "current_counters": {
    "basic": 1,
    "standard": 0,
    "premium": 0
  }
}
```

### Command JSON Structure
```json
{
  "id": "cmd-12345",
  "type": "RESET_COUNTERS",
  "payload": "",
  "timestamp": 1234567890
}
```

## Configuration Parameters

### Treatment Durations
- **Basic**: 5 seconds (5000ms)
- **Standard**: 10 seconds (10000ms)
- **Premium**: 15 seconds (15000ms)

### Network Settings
- **Backend Base URL**: `http://10.49.218.5:8000`
- **Handshake Endpoint**: `/api/handshake/`
- **Events Endpoint**: `/api/device/events/`
- **Commands Endpoint**: `/api/device/{id}/commands/`
- **HTTPS Timeout**: 5000ms
- **Command Poll Interval**: 30000ms (30 seconds)

### Retry Configuration
- **Base Retry Delay**: 2000ms
- **Max Retry Delay**: 300000ms (5 minutes)
- **Jitter Percentage**: 20%
- **Exponential Backoff**: Yes

### WiFi Configuration
- **AP SSID**: "OZONE-CONFIG"
- **AP Password**: "mb95z78y"
- **Default STA SSID**: "testtest"
- **Default STA Password**: "mb95z78y"

## Error Handling & Recovery

### Network Issues
- **WiFi Disconnection**: Automatic reconnection with exponential backoff
- **HTTP Timeouts**: Apply exponential backoff retry
- **401 Unauthorized**: Re-perform device handshake
- **Connection Failures**: Automatic reconnection with smart retry logic
- **Signal Degradation**: RSSI monitoring with proactive warnings

### Storage Issues
- **EEPROM Corruption**: Reset counters to 0, reinitialize
- **LittleFS Mount Failure**: Retry mount operation
- **Queue Full**: Stop queuing new events, show warning

### Hardware Issues
- **RTC Failure**: Use millis() fallback for timestamps
- **Button Bounce**: 50ms debounce delay
- **Relay Failure**: Continue operation, log error
- **WiFi Hardware Issues**: Automatic reconnection attempts with quality monitoring

## Debug Commands (Serial Interface)

### Available Commands
- `b` - Start Basic treatment
- `s` - Start Standard treatment  
- `p` - Start Premium treatment
- `x` (hold 2s) - Stop current treatment
- `r` - Reset counters
- `t` - Test network connectivity
- `o` - Show queue status
- `c` - Poll commands manually
- `q` - Clear command queue
- `d` - Debug command queue
- `j` - JSON test
- `w` - WiFi diagnostics
- `n` - Reconnect WiFi
- `m` - Manual reconnect (force immediate attempt)
- `s` - Advanced WiFi statistics (packet loss, latency, quality score)

## WiFi Reconnection System

### Automatic Reconnection Features
The system includes a robust WiFi reconnection mechanism that ensures continuous operation even during network outages.

#### **Reconnection Strategies**
1. **Periodic Reconnection**: Automatic attempts every 30 seconds when disconnected
2. **Event-Driven Triggers**: Immediate reconnection on network operation failures
3. **Exponential Backoff**: Smart retry intervals (30s → 60s → 120s → 300s max)
4. **Connection Quality Monitoring**: RSSI tracking with degradation warnings

#### **Reconnection Triggers**
- **Handshake Failures**: Connection errors during device registration
- **Upload Failures**: Network errors during event upload
- **Command Polling Failures**: Connection issues during command retrieval
- **Periodic Checks**: Regular reconnection attempts when offline

#### **Smart Features**
- **Jitter**: ±20% randomization to prevent network flooding
- **Quality Monitoring**: RSSI tracking every 10 seconds
- **Packet Loss Detection**: HTTP ping tests every 30 seconds
- **Latency Measurement**: Real-time latency tracking with min/max/avg
- **Connection Quality Scoring**: 0-100 score based on packet loss, latency, and RSSI
- **Graceful Degradation**: Local operations continue during reconnection
- **Automatic RTC Sync**: Time synchronization after successful reconnection

#### **Reconnection Timeline**
```
Disconnection → 30s → 60s → 120s → 300s → 300s (max interval)
                ↓     ↓     ↓      ↓      ↓
              Attempt Attempt Attempt Attempt Attempt
```

#### **Connection Quality Thresholds**
- **Good Signal**: RSSI > -70 dBm
- **Degraded Signal**: RSSI -80 to -70 dBm (warning issued)
- **Poor Signal**: RSSI < -80 dBm (reconnection may be triggered)
- **Critical Signal**: RSSI < -90 dBm (connection unstable warning)

#### **Debug Commands**
- `m` - Force immediate reconnection attempt
- `w` - Display WiFi diagnostics and signal strength
- `s` - Display advanced WiFi statistics (packet loss, latency, quality score)
- `t` - Test network connectivity

## Security Considerations

### Authentication
- Device handshake with MAC address + firmware version
- Bearer token authentication for API calls
- Token refresh via handshake on 401 errors

### Data Integrity
- Unique event IDs prevent duplicate processing
- Reset counter ensures ID uniqueness across reboots
- JSON validation for all network communications

### Network Security
- HTTPS communication (with insecure TLS flag for testing)
- Connection reuse for efficiency
- Timeout handling prevents hanging connections

## Performance Characteristics

### Loop Frequency
- **Main Loop**: 20Hz (50ms delay)
- **Display Update**: 1Hz during treatment
- **Command Poll**: Every 30 seconds
- **Queue Status**: Every 10 seconds (offline)

### Memory Usage
- **EEPROM**: 512 bytes total
- **LittleFS**: Up to 5MB (4MB events + 1MB commands)
- **RAM**: Dynamic JSON documents (256-1024 bytes)

### Power Consumption
- **Active Treatment**: Relay ON + WiFi active
- **Idle**: Low power mode with periodic network checks
- **Offline**: Minimal power, local operations only

## Troubleshooting Guide

### Common Issues

1. **WiFi Connection Failed**
   - Check credentials in EEPROM
   - Verify network availability
   - Use `w` command for diagnostics

2. **Events Not Uploading**
   - Check backend connectivity with `t` command
   - Verify device handshake with `c` command
   - Check queue status with `o` command

3. **Buttons Not Responding**
   - Verify GPIO pin configuration
   - Check for button bounce issues
   - Test with debug commands

4. **WiFi Connection Issues**
   - System automatically attempts reconnection every 30 seconds
   - Use `m` command to force immediate reconnection
   - Check signal strength with `w` command
   - Verify credentials are correct
   - Monitor RSSI levels for signal quality

5. **System Issues**
   - Check web interface for system status
   - Verify network connectivity
   - Use debug commands for troubleshooting

### Debug Procedures

1. **Network Diagnostics**
   ```
   Serial: w (WiFi diagnostics)
   Serial: t (Test connectivity)
   Serial: n (Reconnect WiFi)
   ```

2. **Queue Management**
   ```
   Serial: o (Show queue status)
   Serial: q (Clear command queue)
   Serial: d (Debug command queue)
   ```

3. **System Reset**
   ```
   Serial: r (Reset counters)
   Serial: c (Clear memory - via command)
   ```

## Version Information

- **Firmware Version**: 1.0.0-sim
- **Arduino Framework**: ESP32
- **Last Updated**: January 2025
- **Timezone**: Kuala Lumpur (UTC+8)

---

*This documentation covers the complete flow and operation of the ozone machine system. For technical support or modifications, refer to the source code comments and this flow documentation.*
