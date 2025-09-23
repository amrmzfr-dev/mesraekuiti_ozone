// ====================================================================================
//  OZONE MACHINE FIRMWARE - MAIN ENTRY (single-file layout)
//  Navigation guide:
//   - CONFIGURATION ........................................ around line ~15
//   - GLOBAL OBJECTS ....................................... around line ~60
//   - RUNTIME STATE ........................................ around line ~69
//   - FORWARD DECLARATIONS ................................ around line ~90
//   - BACKEND HELPERS (handshake/events) .................. around line ~129
//   - ARDUINO LIFECYCLE (setup/loop) ...................... around line ~220
//   - INPUT HANDLING (buttons) ............................ around line ~335
//   - TREATMENT CONTROL (start/stop/timer) ................ around line ~437
//   - DISPLAY (screens) ................................... around line ~526
//   - POWER-SAVING (LCD sleep) ............................ around line ~568
//   - HELPERS (names, durations, format) .................. around line ~577
//   - EEPROM PERSISTENCE .................................. around line ~605
//   - WI‑FI + LOCAL WEB UI ................................ around line ~643
// ====================================================================================
#include <Arduino.h>
#include <LiquidCrystal_I2C.h>
#include <Wire.h>
#include <EEPROM.h>
#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoJson.h>
#include <RTClib.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include "pins.h"

// ====================================================================================
//  SECTION: CONFIGURATION (pins are centralized in include/pins.h)
// ====================================================================================

// Relay configuration
#define RELAY_ACTIVE_LOW 1   // Set to 1 if your relay board is active-LOW, 0 for active-HIGH
#define RELAY_ON_LEVEL (RELAY_ACTIVE_LOW ? LOW : HIGH)
#define RELAY_OFF_LEVEL (RELAY_ACTIVE_LOW ? HIGH : LOW)

// ------------------------------------------------------------------------------------
// LCD configuration
#define LCD_COLUMNS 20
#define LCD_ROWS 4

// ------------------------------------------------------------------------------------
// Timer durations (milliseconds)
#define TIMER_BASIC_DURATION 5000     // 5 seconds (testing)
#define TIMER_STANDARD_DURATION 10000 // 10 seconds (testing)
#define TIMER_PREMIUM_DURATION 15000  // 15 seconds (testing)

// ------------------------------------------------------------------------------------
// System timing
#define STARTUP_DELAY 1000           // Wait 1 second after startup before accepting button presses
#define STOP_HOLD_TIME 2000          // Hold SELECT for 2 seconds to stop timer
#define LCD_SLEEP_TIMEOUT 120000     // 2 minutes idle -> backlight off (no sleep during timer)

// ------------------------------------------------------------------------------------
// EEPROM settings
#define EEPROM_SIZE 512              // Size of EEPROM to use
#define COUNTERS_START_ADDR 0        // Starting address for counters storage
#define MAGIC_NUMBER_ADDR 12         // Address to store magic number for validation
#define MAGIC_NUMBER 0x1234          // Magic number to validate data integrity
// Wi-Fi settings
#define WIFI_SSID_ADDR 20            // Starting address for Wi-Fi SSID (max 32 chars)
#define WIFI_PASS_ADDR 60            // Starting address for Wi-Fi password (max 64 chars)
#define WIFI_AP_SSID "OZONE-CONFIG"
#define WIFI_AP_PASS "mb95z78y"
#define WIFI_DEFAULT_SSID "testtest"
#define WIFI_DEFAULT_PASS "mb95z78y"
// Device auth storage
#define DEV_DEVICE_ID_ADDR 140       // device_id start (max 64)
#define DEV_TOKEN_ADDR     204       // token start (max 128)

// ------------------------------------------------------------------------------------
// Backend (production)
#define BACKEND_BASE "https://www.ozone-p2.mesraekuiti.com"
#define URL_HANDSHAKE BACKEND_BASE "/api/handshake/"
#define URL_EVENTS    BACKEND_BASE "/api/device/events/"
#define HTTPS_TIMEOUT_MS 5000
#define USE_INSECURE_TLS 1  // Set 0 when proper root CA is embedded

// ------------------------------------------------------------------------------------
// Web server
#define WEB_SERVER_PORT 80

// ------------------------------------------------------------------------------------
// Event queue configuration
#define EVENT_QUEUE_FILE "/events.jsonl"
#define MAX_QUEUE_SIZE (4 * 1024 * 1024)  // 4MB max queue size
#define MAX_RETRY_ATTEMPTS 10
#define RETRY_BASE_DELAY_MS 2000
#define RETRY_MAX_DELAY_MS 300000  // 5 minutes
#define RETRY_JITTER_PERCENT 20

// ====================================================================================
//  SECTION: GLOBAL OBJECTS
// ====================================================================================
// LCD object
LiquidCrystal_I2C lcd(LCD_ADDRESS, LCD_COLUMNS, LCD_ROWS);

// RTC object
RTC_DS3231 rtc;

// Web server
WebServer server(WEB_SERVER_PORT);

// ====================================================================================
//  SECTION: RUNTIME STATE
// ====================================================================================
// System state
bool systemReady = false;
bool displayNeedsUpdate = true;
bool lcdSleeping = false;
bool timerActive = false;
unsigned long timerStartTime = 0;
unsigned long timerRemaining = 0;
unsigned long lastInteractionTime = 0;
int currentTreatment = 0; // 0=BASIC, 1=STANDARD, 2=PREMIUM

// Counters
int counters[3] = {0, 0, 0}; // B, S, P

// Backend device identity
String g_deviceId = "";
String g_deviceToken = "";
String g_firmware = "1.0.0";

// Provisioning/assignment placeholder (for web UI status)
bool deviceAssigned = false;

// Event queue state
bool queueInitialized = false;
unsigned long lastUploadAttempt = 0;
int currentRetryDelay = RETRY_BASE_DELAY_MS;
int retryAttempts = 0;

// ====================================================================================
//  SECTION: RTOS PRIMITIVES (Queues/Tasks)
// ====================================================================================
enum ControlMsgType { CTL_START_B = 0, CTL_START_S = 1, CTL_START_P = 2, CTL_STOP = 3 };
typedef struct {
  ControlMsgType type;
} ControlMsg;

typedef struct {
  char treatment[10]; // "BASIC"|"STANDARD"|"PREMIUM"
  int counter;
} NetEvent;

// Queues
static QueueHandle_t g_controlQueue = nullptr;   // Button/input → control
static QueueHandle_t g_netQueue = nullptr;       // Control → network (treatment started)

// Task handles
static TaskHandle_t hTaskInput = nullptr;
static TaskHandle_t hTaskControl = nullptr;
static TaskHandle_t hTaskDisplay = nullptr;
static TaskHandle_t hTaskNet = nullptr;

// ====================================================================================
//  SECTION: FORWARD DECLARATIONS
// ====================================================================================
// Function declarations (existing)
// Task forward declarations
void TaskInput(void*);
void TaskControl(void*);
void TaskDisplay(void*);
void TaskNet(void*);
void handleButtons();
void startTreatment(int treatmentIdx);
void stopTreatment();
void updateTimer();
void updateDisplay();
void updateTimerDisplay();
void handleLCDSleep();
String getTreatmentName(int treatmentIdx);
unsigned long getTreatmentDuration(int treatmentIdx);
String formatTime(unsigned long milliseconds);
void saveCountersToEEPROM();
void loadCountersFromEEPROM();
void setupWiFi();
void setupWebServer();
void handleRoot();
void handleWiFiConfig();
void handleStatus();
void handleCounters();
void saveWiFiCredentials(const String& ssid, const String& password);
void loadWiFiCredentials(String& ssid, String& password);

// Event queue functions
bool initializeEventQueue();
bool appendEventToQueue(const String& eventJson);
bool processEventQueue();
String readNextEventFromQueue();
bool removeEventFromQueue();
bool isQueueEmpty();
size_t getQueueSize();
void resetRetryDelay();
int calculateRetryDelay();

// ====================================================================================
//  SECTION: BACKEND HELPERS (handshake + event upload)
// ====================================================================================
void saveDeviceAuthToEEPROM(const String &devId, const String &token) {
  // device_id (max 64)
  for (int i = 0; i < (int)devId.length() && i < 64; i++) EEPROM.write(DEV_DEVICE_ID_ADDR + i, devId[i]);
  EEPROM.write(DEV_DEVICE_ID_ADDR + min(63, (int)devId.length()), 0);
  // token (max 128)
  for (int i = 0; i < (int)token.length() && i < 128; i++) EEPROM.write(DEV_TOKEN_ADDR + i, token[i]);
  EEPROM.write(DEV_TOKEN_ADDR + min(127, (int)token.length()), 0);
  EEPROM.commit();
}

void loadDeviceAuthFromEEPROM(String &devId, String &token) {
  devId = ""; token = "";
  for (int i = 0; i < 64; i++) { char c = EEPROM.read(DEV_DEVICE_ID_ADDR + i); if (c == 0 || c == 255) break; devId += c; }
  for (int i = 0; i < 128; i++) { char c = EEPROM.read(DEV_TOKEN_ADDR + i); if (c == 0 || c == 255) break; token += c; }
}

bool performHandshake() {
  WiFiClientSecure client;
#if USE_INSECURE_TLS
  client.setInsecure();
#endif
  HTTPClient http;
  if (!http.begin(client, URL_HANDSHAKE)) return false;
  http.setTimeout(HTTPS_TIMEOUT_MS);
  http.addHeader("Content-Type", "application/json");
  String mac = WiFi.macAddress();
  JsonDocument body;
  body["mac"] = mac;
  body["firmware"] = g_firmware;
  String payload; serializeJson(body, payload);
  int code = http.POST(payload);
  if (code > 0) {
    String resp = http.getString();
    JsonDocument doc;
    if (deserializeJson(doc, resp) == DeserializationError::Ok) {
      String devId = doc["device_id"].as<String>();
      String token = doc["token"].as<String>();
      bool assigned = doc["assigned"].as<bool>();
      if (devId.length() > 0 && token.length() > 0) {
        g_deviceId = devId; g_deviceToken = token;
        saveDeviceAuthToEEPROM(g_deviceId, g_deviceToken);
        deviceAssigned = assigned;
        Serial.printf("Handshake OK. device_id=%s assigned=%d\n", g_deviceId.c_str(), assigned);
        http.end();
        return true;
      }
    }
  } else {
    Serial.printf("Handshake HTTP error: %d\n", code);
  }
  http.end();
  return false;
}

String generateEventId(const String &deviceId, unsigned long counterVal) {
  // Simple monotonic: deviceId + millis
  char buf[64];
  snprintf(buf, sizeof(buf), "%s-%010lu", deviceId.c_str(), (unsigned long)millis());
  return String(buf);
}

bool postTreatmentEvent(const String &treatment, int counterVal, const String &isoTs) {
  if (g_deviceId.isEmpty() || g_deviceToken.isEmpty()) {
    Serial.println("Missing device auth; performing handshake...");
    if (!performHandshake()) return false;
  }
  
  // Create event JSON
  JsonDocument body;
  body["device_id"] = g_deviceId;
  body["firmware"] = g_firmware;
  body["event_id"] = generateEventId(g_deviceId, (unsigned long)counterVal);
  body["event"] = "treatment";
  body["treatment"] = treatment;
  body["counter"] = counterVal;
  body["ts"] = isoTs;
  String payload; 
  serializeJson(body, payload);
  
  // Append to queue instead of direct HTTP
  bool success = appendEventToQueue(payload);
  if (success) {
    Serial.printf("Event queued: %s\n", treatment.c_str());
  } else {
    Serial.printf("Failed to queue event: %s\n", treatment.c_str());
  }
  
  return success;
}

String nowIsoTimestamp() {
  // Use RTC if available; else approximate from millis (not ideal, but fallback)
  DateTime now = rtc.now();
  char ts[25];
  snprintf(ts, sizeof(ts), "%04d-%02d-%02dT%02d:%02d:%02dZ", now.year(), now.month(), now.day(), now.hour(), now.minute(), now.second());
  return String(ts);
}

// ====================================================================================
//  SECTION: ARDUINO LIFECYCLE
// ====================================================================================
void setup() {
  Serial.begin(115200);
  delay(1000); // Reduced from 2000ms
  
  Serial.println("=== OZONE MACHINE SYSTEM ===");
  Serial.println("Initializing...");
  
  // Initialize I2C and LCD FIRST
  Wire.begin(LCD_SDA_PIN, LCD_SCL_PIN);
  lcd.init();
  lcd.backlight();
  lcd.clear();
  
  // Initialize RTC on separate I2C bus
  Wire1.begin(RTC_SDA_PIN, RTC_SCL_PIN);
  if (rtc.begin(&Wire1)) {
    Serial.println("RTC initialized successfully");
    
    // Check if RTC lost power and set time if needed
    if (rtc.lostPower()) {
      Serial.println("RTC lost power, setting time to compile time");
      rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
    }
    
    // Print current RTC time
    DateTime now = rtc.now();
    Serial.print("Current RTC time: ");
    Serial.println(now.timestamp());
  } else {
    Serial.println("RTC initialization failed!");
  }
  
  // Show booting message immediately
  lcd.setCursor(4, 0);
  lcd.print("BOOTING UP...");
  lcd.setCursor(2, 1);
  lcd.print("PLEASE WAIT");
  lcd.setCursor(3, 2);
  lcd.print("OZONE MACHINE");
  lcd.setCursor(4, 3);
  lcd.print("STARTING...");
  
  // Initialize buttons
  pinMode(BUTTON_UP_PIN, INPUT_PULLUP);      // BASIC
  pinMode(BUTTON_DOWN_PIN, INPUT_PULLUP);    // STANDARD
  pinMode(BUTTON_SELECT_PIN, INPUT_PULLUP);  // PREMIUM
  
  // Initialize relay (single channel)
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, RELAY_OFF_LEVEL);
  
  // Initialize EEPROM
  EEPROM.begin(EEPROM_SIZE);
  loadCountersFromEEPROM();
  
  // Initialize LittleFS for event queue
  if (!LittleFS.begin(true)) {
    Serial.println("LittleFS initialization failed!");
  } else {
    Serial.println("LittleFS initialized successfully");
    initializeEventQueue();
  }
  
  // Setup Wi-Fi and web server (this takes time)
  setupWiFi();
  setupWebServer();
  
  // Load any saved device auth and perform handshake on boot when online
  loadDeviceAuthFromEEPROM(g_deviceId, g_deviceToken);
  Serial.printf("Loaded auth from EEPROM: device_id='%s' token_len=%d\n", g_deviceId.c_str(), (int)g_deviceToken.length());
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("Performing handshake to announce presence...");
    bool ok = performHandshake();
    Serial.printf("Handshake result: %s\n", ok ? "OK" : "FAILED");
  } else {
    Serial.println("Wi-Fi not connected; skipping handshake");
  }
  
  // Initialize system state
  systemReady = false;
  timerActive = false;
  lastInteractionTime = millis();
  
  // Display main screen
  updateDisplay();
  
  Serial.println("System initialized successfully!");
  Serial.println("Waiting 1 second before accepting button input...");

  // ==================================================================================
  // Create RTOS Queues
  g_controlQueue = xQueueCreate(16, sizeof(ControlMsg));
  g_netQueue = xQueueCreate(8, sizeof(NetEvent));
  
  // Create RTOS Tasks
#if CONFIG_FREERTOS_UNICORE
  const BaseType_t coreUI = 0;
  const BaseType_t coreNET = 0;
#else
  const BaseType_t coreUI = 1;   // APP core
  const BaseType_t coreNET = 0;  // PRO core
#endif
  xTaskCreatePinnedToCore(TaskInput,   "TaskInput",   4096, nullptr, 4, &hTaskInput, coreUI);
  xTaskCreatePinnedToCore(TaskControl, "TaskControl", 4096, nullptr, 3, &hTaskControl, coreUI);
  xTaskCreatePinnedToCore(TaskDisplay, "TaskDisplay", 4096, nullptr, 2, &hTaskDisplay, coreUI);
  xTaskCreatePinnedToCore(TaskNet,     "TaskNet",     6144, nullptr, 1, &hTaskNet,     coreNET);
}

void loop() {
  // Idle loop – RTOS tasks handle the workload now
  vTaskDelay(pdMS_TO_TICKS(250));
}

// ====================================================================================
//  SECTION: INPUT HANDLING (buttons + long-press stop)
// ====================================================================================
void handleButtons() {
  // Simple button reading - no bullshit debouncing
  bool basicPressed = (digitalRead(BUTTON_UP_PIN) == LOW);
  bool standardPressed = (digitalRead(BUTTON_DOWN_PIN) == LOW);
  bool premiumPressed = (digitalRead(BUTTON_SELECT_PIN) == LOW);

  // Static state for PREMIUM long-press tracking and guards
  static unsigned long premiumPressStartMs = 0;
  static bool premiumBlockUntilRelease = false; // prevents auto-start after long-press stop
  static bool premiumReleasedSinceStart = true; // must release after starting before long-press can stop

  // Debug output
  static unsigned long lastDebugTime = 0;
  if (millis() - lastDebugTime > 2000) {
    lastDebugTime = millis();
    Serial.print("Buttons - B:");
    Serial.print(basicPressed ? "PRESSED" : "released");
    Serial.print(" S:");
    Serial.print(standardPressed ? "PRESSED" : "released");
    Serial.print(" P:");
    Serial.print(premiumPressed ? "PRESSED" : "released");
    Serial.print(" Ready:");
    Serial.print(systemReady ? "YES" : "NO");
    Serial.print(" Active:");
    Serial.println(timerActive ? "YES" : "NO");
  }

  // During an active timer: ignore BASIC/STANDARD short presses.
  // Only allow PREMIUM long-press (>= STOP_HOLD_TIME) to stop, and only
  // if PREMIUM has been released at least once since the timer started.
  if (timerActive) {
    if (premiumPressed) {
      if (!premiumReleasedSinceStart) {
        // Still the same hold that started PREMIUM; ignore until released
        return;
      }
      if (premiumPressStartMs == 0) {
        premiumPressStartMs = millis();
      }
      if (millis() - premiumPressStartMs >= STOP_HOLD_TIME) {
        Serial.println("PREMIUM long press - stopping treatment");
        stopTreatment();
        premiumPressStartMs = 0;
        premiumBlockUntilRelease = true; // require release before any future PREMIUM start
      }
    } else {
      // PREMIUM released; after this, long-press can be recognized
      premiumReleasedSinceStart = true;
      premiumPressStartMs = 0;
    }

    // Wake up LCD on any press
    if ((basicPressed || standardPressed || premiumPressed) && lcdSleeping) {
      lcd.backlight();
      lcdSleeping = false;
      lastInteractionTime = millis();
    }
    return; // Do not process start logic while active
  }

  // If not active: handle starting treatments on short press
  if (systemReady) {
    // Enforce release-guard for PREMIUM after a long-press stop
    if (premiumBlockUntilRelease) {
      if (!premiumPressed) {
        premiumBlockUntilRelease = false; // cleared on full release
      }
      // While still held, ignore any PREMIUM start
      if (premiumPressed) return;
    }

    if (basicPressed) {
      Serial.println("BASIC button pressed - starting treatment");
      startTreatment(0);
      premiumReleasedSinceStart = true;  // PREMIUM not held to start
      delay(200); // Simple delay to prevent multiple presses
    } else if (standardPressed) {
      Serial.println("STANDARD button pressed - starting treatment");
      startTreatment(1);
      premiumReleasedSinceStart = true;  // PREMIUM not held to start
      delay(200);
    } else if (premiumPressed) {
      Serial.println("PREMIUM button pressed - starting treatment");
      startTreatment(2);
      premiumReleasedSinceStart = false; // must release before long-press can stop
      delay(200);
    } else {
      // Reset long-press tracker when idle
      premiumPressStartMs = 0;
    }
  } else if (basicPressed || standardPressed || premiumPressed) {
    Serial.println("Button pressed but system not ready");
  }

  // Wake up LCD on any button press
  if ((basicPressed || standardPressed || premiumPressed) && lcdSleeping) {
    lcd.backlight();
    lcdSleeping = false;
    lastInteractionTime = millis();
  }
}

// ====================================================================================
//  SECTION: TREATMENT CONTROL (start/stop/timer)
// ====================================================================================
void startTreatment(int treatmentIdx) {
  if (timerActive) {
    Serial.println("Timer already active, ignoring button press");
    return;
  }
  
  currentTreatment = treatmentIdx;
  timerStartTime = millis();
  timerActive = true;
  
  // Increment counter immediately
  counters[treatmentIdx]++;
  saveCountersToEEPROM();
  
  // Activate relay
  digitalWrite(RELAY_PIN, RELAY_ON_LEVEL);
  
  // Wake up LCD
  lcd.backlight();
  lcdSleeping = false;
  lastInteractionTime = millis();
  displayNeedsUpdate = true;
  
  // Log treatment with timestamp
  DateTime now = rtc.now();
  Serial.println("=== TREATMENT STARTED ===");
  Serial.print("Treatment: ");
  Serial.println(getTreatmentName(treatmentIdx));
  Serial.print("Counter: ");
  Serial.println(counters[treatmentIdx]);
  
  // Build ISO timestamp and send event to backend
  String isoTs = nowIsoTimestamp();
  String treatmentName = getTreatmentName(treatmentIdx);
  // Map to BASIC/STANDARD/PREMIUM token
  String tkn = (treatmentIdx == 0) ? "BASIC" : (treatmentIdx == 1) ? "STANDARD" : "PREMIUM";
  postTreatmentEvent(tkn, counters[treatmentIdx], isoTs);
}

void stopTreatment() {
  timerActive = false;
  digitalWrite(RELAY_PIN, RELAY_OFF_LEVEL);
  displayNeedsUpdate = true;
  
  // Log treatment stop with timestamp
  DateTime now = rtc.now();
  Serial.println("=== TREATMENT STOPPED ===");
  Serial.print("Treatment: ");
  Serial.println(getTreatmentName(currentTreatment));
  Serial.print("Timestamp: ");
  Serial.println(now.timestamp());
  Serial.println("Stopped by user");
  Serial.println("========================");
}

void updateTimer() {
  unsigned long elapsed = millis() - timerStartTime;
  unsigned long totalDuration = getTreatmentDuration(currentTreatment);
  
  if (elapsed >= totalDuration) {
    // Timer completed
    timerActive = false;
    digitalWrite(RELAY_PIN, RELAY_OFF_LEVEL);
    displayNeedsUpdate = true;
    
    // Log treatment completion with timestamp
    DateTime now = rtc.now();
    Serial.println("=== TREATMENT COMPLETED ===");
    Serial.print("Treatment: ");
    Serial.println(getTreatmentName(currentTreatment));
    Serial.print("Timestamp: ");
    Serial.println(now.timestamp());
    Serial.print("Duration: ");
    Serial.print(totalDuration / 1000);
    Serial.println(" seconds");
    Serial.println("Completed naturally");
    Serial.println("========================");
  } else {
    // Update timer display only every second
    static unsigned long lastTimerUpdate = 0;
    timerRemaining = totalDuration - elapsed;
    
    if (millis() - lastTimerUpdate > 1000) { // Update timer display every 1 second
      updateTimerDisplay();
      lastTimerUpdate = millis();
    }
  }
}

// ====================================================================================
//  SECTION: DISPLAY (main/timer screens)
// ====================================================================================
void updateDisplay() {
  lcd.clear();
  
  if (!systemReady) {
    // Startup message
    lcd.setCursor(4, 0);
    lcd.print("INITIALIZING");
    lcd.setCursor(3, 1);
    lcd.print("PLEASE WAIT...");
    lcd.setCursor(2, 2);
    lcd.print("OZONE MACHINE");
    lcd.setCursor(4, 3);
    lcd.print("STARTING UP");
  } else if (timerActive) {
    // Timer screen
    lcd.setCursor((LCD_COLUMNS - getTreatmentName(currentTreatment).length()) / 2, 0);
    lcd.print(getTreatmentName(currentTreatment));
    lcd.setCursor(5, 1);
    lcd.print("TREATMENT");
    lcd.setCursor(6, 2);
    lcd.print(formatTime(timerRemaining));
    lcd.setCursor(7, 3);
    lcd.print("ACTIVE");
  } else {
    // Main screen
    lcd.setCursor(3, 0);
    lcd.print("OZONE MACHINE");
    lcd.setCursor(2, 1);
    lcd.printf("%04d %04d %04d", counters[0], counters[1], counters[2]);
    lcd.setCursor(4, 2);
    lcd.print(" B   S   P ");
    lcd.setCursor(3, 3);
    lcd.print("BASIC STD PREM");
  }
}

void updateTimerDisplay() {
  // Only update the timer digits to prevent flicker
  lcd.setCursor(6, 2);
  lcd.print(formatTime(timerRemaining));
}

// ====================================================================================
//  SECTION: POWER-SAVING (LCD backlight sleep)
// ====================================================================================
void handleLCDSleep() {
  if (!timerActive && systemReady) {
    if (millis() - lastInteractionTime > LCD_SLEEP_TIMEOUT && !lcdSleeping) {
      lcd.noBacklight();
      lcdSleeping = true;
    }
  }
}

// ====================================================================================
//  SECTION: HELPERS (names, durations, time formatting)
// ====================================================================================
String getTreatmentName(int treatmentIdx) {
  switch (treatmentIdx) {
    case 0: return String("BASIC TREATMENT");
    case 1: return String("STANDARD TREATMENT");
    case 2: return String("PREMIUM TREATMENT");
    default: return String("UNKNOWN");
  }
}

unsigned long getTreatmentDuration(int treatmentIdx) {
  switch (treatmentIdx) {
    case 0: return TIMER_BASIC_DURATION;
    case 1: return TIMER_STANDARD_DURATION;
    case 2: return TIMER_PREMIUM_DURATION;
    default: return 0;
  }
}

String formatTime(unsigned long milliseconds) {
  unsigned long totalSeconds = milliseconds / 1000;
  unsigned long minutes = totalSeconds / 60;
  unsigned long seconds = totalSeconds % 60;
  
  char timeStr[6];
  sprintf(timeStr, "%02lu:%02lu", minutes, seconds);
  return String(timeStr);
}

// ====================================================================================
//  SECTION: EEPROM PERSISTENCE (counters + credentials)
// ====================================================================================
void saveCountersToEEPROM() {
  for (int i = 0; i < 3; i++) {
    EEPROM.write(COUNTERS_START_ADDR + i * 4, (counters[i] >> 24) & 0xFF);
    EEPROM.write(COUNTERS_START_ADDR + i * 4 + 1, (counters[i] >> 16) & 0xFF);
    EEPROM.write(COUNTERS_START_ADDR + i * 4 + 2, (counters[i] >> 8) & 0xFF);
    EEPROM.write(COUNTERS_START_ADDR + i * 4 + 3, counters[i] & 0xFF);
  }
  
  // Write magic number
  EEPROM.write(MAGIC_NUMBER_ADDR, (MAGIC_NUMBER >> 8) & 0xFF);
  EEPROM.write(MAGIC_NUMBER_ADDR + 1, MAGIC_NUMBER & 0xFF);
  EEPROM.commit();
}

void loadCountersFromEEPROM() {
  // Check magic number
  uint16_t storedMagic = (EEPROM.read(MAGIC_NUMBER_ADDR) << 8) | EEPROM.read(MAGIC_NUMBER_ADDR + 1);
  
  if (storedMagic == MAGIC_NUMBER) {
    // Load counters
    for (int i = 0; i < 3; i++) {
      counters[i] = (EEPROM.read(COUNTERS_START_ADDR + i * 4) << 24) |
                   (EEPROM.read(COUNTERS_START_ADDR + i * 4 + 1) << 16) |
                   (EEPROM.read(COUNTERS_START_ADDR + i * 4 + 2) << 8) |
                   EEPROM.read(COUNTERS_START_ADDR + i * 4 + 3);
    }
    Serial.println("Counters loaded from EEPROM");
  } else {
    Serial.println("No valid data in EEPROM, initializing to 0");
    for (int i = 0; i < 3; i++) {
      counters[i] = 0;
    }
    saveCountersToEEPROM();
  }
  
  Serial.printf("Counters: B=%d S=%d P=%d\n", counters[0], counters[1], counters[2]);
}

// ====================================================================================
//  SECTION: WI‑FI + LOCAL WEB UI
// ====================================================================================
// Wi-Fi and Web Server Functions
void setupWiFi() {
  // Load Wi-Fi credentials from EEPROM
  String ssid, password;
  loadWiFiCredentials(ssid, password);
  
  Serial.print("Loaded from EEPROM - SSID: '");
  Serial.print(ssid);
  Serial.print("' Password: '");
  Serial.print(password);
  Serial.println("'");
  
  // If no valid credentials in EEPROM, clear and save default ones
  if (ssid.length() == 0 || ssid.length() > 32) {
    Serial.println("Invalid Wi-Fi credentials found, clearing EEPROM and saving defaults...");
    
    // Clear Wi-Fi section of EEPROM
    for (int i = WIFI_SSID_ADDR; i < WIFI_SSID_ADDR + 32; i++) {
      EEPROM.write(i, 0);
    }
    for (int i = WIFI_PASS_ADDR; i < WIFI_PASS_ADDR + 64; i++) {
      EEPROM.write(i, 0);
    }
    EEPROM.commit();
    
    // Save default credentials
    saveWiFiCredentials(WIFI_DEFAULT_SSID, WIFI_DEFAULT_PASS);
    ssid = WIFI_DEFAULT_SSID;
    password = WIFI_DEFAULT_PASS;
    
    Serial.println("Default credentials saved to EEPROM");
  }
  
  // Try to connect to stored Wi-Fi
  if (ssid.length() > 0) {
    Serial.print("Connecting to Wi-Fi: ");
    Serial.println(ssid);
    WiFi.begin(ssid.c_str(), password.c_str());
    
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 10) {
      delay(300);
      Serial.print(".");
      attempts++;
    }
    
    if (WiFi.status() == WL_CONNECTED) {
      Serial.println();
      Serial.print("Wi-Fi connected! IP address: ");
      Serial.println(WiFi.localIP());
      return;
    } else {
      Serial.println();
      Serial.print("Wi-Fi connection failed. Status: ");
      Serial.println(WiFi.status());
    }
  }
  
  // If connection failed, start AP mode
  Serial.println("Starting AP mode...");
  WiFi.mode(WIFI_AP);
  WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASS);
  Serial.print("AP started! SSID: ");
  Serial.print(WIFI_AP_SSID);
  Serial.print(" Password: ");
  Serial.println(WIFI_AP_PASS);
  Serial.print("AP IP address: ");
  Serial.println(WiFi.softAPIP());
}

void setupWebServer() {
  server.on("/", handleRoot);
  server.on("/wifi", HTTP_POST, handleWiFiConfig);
  server.on("/status", handleStatus);
  server.on("/counters", HTTP_POST, handleCounters);
  server.begin();
  Serial.println("Web server started");
}

void handleRoot() {
  String html = "<!DOCTYPE html><html><head><title>Ozone Machine Config</title>";
  html += "<meta name='viewport' content='width=device-width, initial-scale=1'>";
  html += "<style>body{font-family:Arial;margin:20px;background:#f0f0f0;}";
  html += ".container{max-width:420px;margin:0 auto;background:white;padding:20px;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,0.1);}";
  html += "h1{color:#333;text-align:center;}label{display:block;margin:8px 0 4px;}";
  html += "input[type=text],input[type=password],input[type=number]{width:100%;padding:10px;margin:5px 0;border:1px solid #ddd;border-radius:5px;box-sizing:border-box;}";
  html += "button{width:100%;padding:12px;background:#007bff;color:white;border:none;border-radius:5px;cursor:pointer;font-size:16px;margin-top:8px;}";
  html += "button:hover{background:#0056b3;}";
  html += ".status{background:#e9ecef;padding:10px;border-radius:5px;margin:10px 0;}";
  html += "hr{border:none;border-top:1px solid #eee;margin:16px 0;}";
  html += "</style></head><body>";
  html += "<div class='container'>";
  html += "<h1>Ozone Machine Config</h1>";
  html += "<div class='status'>";
  html += "<strong>Status:</strong> ";
  if (WiFi.getMode() == WIFI_AP) {
    html += "AP Mode - " + String(WIFI_AP_SSID) + "<br>";
    html += "<strong>IP:</strong> " + WiFi.softAPIP().toString();
  } else {
    html += "Connected to " + WiFi.SSID() + "<br>";
    html += "<strong>IP:</strong> " + WiFi.localIP().toString();
  }
  html += "</div>";
  
  // Wi-Fi form
  html += "<form method='POST' action='/wifi'>";
  html += "<h3>Wi-Fi Configuration</h3>";
  html += "<label>SSID</label><input type='text' name='ssid' placeholder='Wi-Fi SSID' value='" + WiFi.SSID() + "' required>";
  html += "<label>Password</label><input type='password' name='password' placeholder='Wi-Fi Password' required>";
  html += "<button type='submit'>Save & Connect</button>";
  html += "</form>";

  html += "<hr>";

  // Counters edit form
  html += "<form method='POST' action='/counters'>";
  html += "<h3>Device Status</h3>";
  html += "<div class='status'>";
  html += "<strong>Assigned:</strong> " + String(deviceAssigned ? "Yes" : "Not Assigned") + "<br>";
  html += "</div>";
  html += "<h3>Counters (editable)</h3>";
  html += "<label>Basic (B)</label><input type='number' name='b' min='0' max='999999' value='" + String(counters[0]) + "'>";
  html += "<label>Standard (S)</label><input type='number' name='s' min='0' max='999999' value='" + String(counters[1]) + "'>";
  html += "<label>Premium (P)</label><input type='number' name='p' min='0' max='999999' value='" + String(counters[2]) + "'>";
  html += "<button type='submit'>Save Counters</button>";
  html += "</form>";

  html += "<p><a href='/status'>Refresh Status</a></p>";
  html += "</div></body></html>";
  
  server.send(200, "text/html", html);
}

void handleWiFiConfig() {
  if (server.hasArg("ssid") && server.hasArg("password")) {
    String ssid = server.arg("ssid");
    String password = server.arg("password");
    
    // Save credentials to EEPROM
    saveWiFiCredentials(ssid, password);
    
    Serial.println("Wi-Fi credentials saved. Restarting...");
    server.send(200, "text/html", "<!DOCTYPE html><html><head><meta http-equiv='refresh' content='5;url=/'></head><body><h1>Wi-Fi credentials saved!</h1><p>Restarting in 5 seconds...</p></body></html>");
    
    delay(2000);
    ESP.restart();
  } else {
    server.send(400, "text/plain", "Missing SSID or password");
  }
}

void handleStatus() {
  JsonDocument doc;
  doc["wifi_mode"] = (WiFi.getMode() == WIFI_AP) ? "AP" : "STA";
  doc["wifi_ssid"] = WiFi.SSID();
  doc["wifi_ip"] = (WiFi.getMode() == WIFI_AP) ? WiFi.softAPIP().toString() : WiFi.localIP().toString();
  doc["counters"]["basic"] = counters[0];
  doc["counters"]["standard"] = counters[1];
  doc["counters"]["premium"] = counters[2];
  doc["device_assigned"] = deviceAssigned;
  
  String response;
  serializeJson(doc, response);
  server.send(200, "application/json", response);
}

void handleCounters() {
  if (!server.hasArg("b") || !server.hasArg("s") || !server.hasArg("p")) {
    server.send(400, "text/plain", "Missing counter values");
    return;
  }
  long b = server.arg("b").toInt();
  long s = server.arg("s").toInt();
  long p = server.arg("p").toInt();

  if (b < 0) b = 0; if (s < 0) s = 0; if (p < 0) p = 0;
  if (b > 999999) b = 999999; if (s > 999999) s = 999999; if (p > 999999) p = 999999;

  counters[0] = (int)b;
  counters[1] = (int)s;
  counters[2] = (int)p;
  saveCountersToEEPROM();
  displayNeedsUpdate = true;

  Serial.printf("Counters updated via web: B=%ld S=%ld P=%ld\n", b, s, p);

  server.send(200, "text/html", "<!DOCTYPE html><html><head><meta http-equiv='refresh' content='0;url=/'></head><body>OK</body></html>");
}

void saveWiFiCredentials(const String& ssid, const String& password) {
  // Save SSID
  for (int i = 0; i < ssid.length() && i < 32; i++) {
    EEPROM.write(WIFI_SSID_ADDR + i, ssid[i]);
  }
  EEPROM.write(WIFI_SSID_ADDR + ssid.length(), 0); // null terminator
  
  // Save password
  for (int i = 0; i < password.length() && i < 64; i++) {
    EEPROM.write(WIFI_PASS_ADDR + i, password[i]);
  }
  EEPROM.write(WIFI_PASS_ADDR + password.length(), 0); // null terminator
  EEPROM.commit();
  
  Serial.println("Wi-Fi credentials saved to EEPROM");
}

void loadWiFiCredentials(String& ssid, String& password) {
  // Load SSID
  ssid = "";
  for (int i = 0; i < 32; i++) {
    char c = EEPROM.read(WIFI_SSID_ADDR + i);
    if (c == 0 || c == 255) break; // Stop at null terminator or uninitialized EEPROM (255)
    if (c >= 32 && c <= 126) { // Only add printable ASCII characters
      ssid += c;
    }
  }
  
  // Load password
  password = "";
  for (int i = 0; i < 64; i++) {
    char c = EEPROM.read(WIFI_PASS_ADDR + i);
    if (c == 0 || c == 255) break; // Stop at null terminator or uninitialized EEPROM (255)
    if (c >= 32 && c <= 126) { // Only add printable ASCII characters
      password += c;
    }
  }
}

// ====================================================================================
//  SECTION: EVENT QUEUE IMPLEMENTATION
// ====================================================================================

bool initializeEventQueue() {
  if (queueInitialized) return true;
  
  // Check if queue file exists, create if not
  if (!LittleFS.exists(EVENT_QUEUE_FILE)) {
    File file = LittleFS.open(EVENT_QUEUE_FILE, "w");
    if (!file) {
      Serial.println("Failed to create event queue file");
      return false;
    }
    file.close();
    Serial.println("Created new event queue file");
  }
  
  queueInitialized = true;
  Serial.printf("Event queue initialized. Size: %zu bytes\n", getQueueSize());
  return true;
}

bool appendEventToQueue(const String& eventJson) {
  if (!queueInitialized) {
    if (!initializeEventQueue()) return false;
  }
  
  // Check queue size limit
  size_t currentSize = getQueueSize();
  if (currentSize > MAX_QUEUE_SIZE) {
    Serial.println("Event queue size limit reached, dropping event");
    return false;
  }
  
  File file = LittleFS.open(EVENT_QUEUE_FILE, "a");
  if (!file) {
    Serial.println("Failed to open event queue file for append");
    return false;
  }
  
  file.println(eventJson);
  file.close();
  
  Serial.printf("Event appended to queue. New size: %zu bytes\n", getQueueSize());
  return true;
}

String readNextEventFromQueue() {
  if (!queueInitialized || isQueueEmpty()) return "";
  
  File file = LittleFS.open(EVENT_QUEUE_FILE, "r");
  if (!file) {
    Serial.println("Failed to open event queue file for read");
    return "";
  }
  
  String event = file.readStringUntil('\n');
  file.close();
  
  return event;
}

bool removeEventFromQueue() {
  if (!queueInitialized || isQueueEmpty()) return false;
  
  // Read all events except the first one
  File file = LittleFS.open(EVENT_QUEUE_FILE, "r");
  if (!file) {
    Serial.println("Failed to open event queue file for removal");
    return false;
  }
  
  String content = "";
  String line = file.readStringUntil('\n'); // Skip first line
  while (file.available()) {
    content += file.readStringUntil('\n') + "\n";
  }
  file.close();
  
  // Write back without the first line
  file = LittleFS.open(EVENT_QUEUE_FILE, "w");
  if (!file) {
    Serial.println("Failed to open event queue file for write");
    return false;
  }
  
  file.print(content);
  file.close();
  
  return true;
}

bool isQueueEmpty() {
  if (!queueInitialized) return true;
  
  File file = LittleFS.open(EVENT_QUEUE_FILE, "r");
  if (!file) return true;
  
  bool isEmpty = !file.available();
  file.close();
  return isEmpty;
}

size_t getQueueSize() {
  if (!queueInitialized) return 0;
  
  File file = LittleFS.open(EVENT_QUEUE_FILE, "r");
  if (!file) return 0;
  
  size_t size = file.size();
  file.close();
  return size;
}

void resetRetryDelay() {
  currentRetryDelay = RETRY_BASE_DELAY_MS;
  retryAttempts = 0;
}

int calculateRetryDelay() {
  if (retryAttempts >= MAX_RETRY_ATTEMPTS) {
    return RETRY_MAX_DELAY_MS;
  }
  
  int delay = currentRetryDelay;
  currentRetryDelay = min(currentRetryDelay * 2, RETRY_MAX_DELAY_MS);
  retryAttempts++;
  
  // Add jitter (±20%)
  int jitter = (delay * RETRY_JITTER_PERCENT) / 100;
  int jitterValue = random(-jitter, jitter + 1);
  
  return max(delay + jitterValue, 1000); // Minimum 1 second
}

bool processEventQueue() {
  if (isQueueEmpty()) return true;
  
  String eventJson = readNextEventFromQueue();
  if (eventJson.isEmpty()) return false;
  
  // Parse event JSON
  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, eventJson);
  if (error) {
    Serial.printf("Failed to parse event JSON: %s\n", error.c_str());
    removeEventFromQueue(); // Remove malformed event
    return false;
  }
  
  // Send HTTP request
  WiFiClientSecure client;
#if USE_INSECURE_TLS
  client.setInsecure();
#endif
  HTTPClient http;
  if (!http.begin(client, URL_EVENTS)) {
    Serial.println("Failed to begin HTTP client");
    return false;
  }
  
  http.setTimeout(HTTPS_TIMEOUT_MS);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", String("Bearer ") + g_deviceToken);
  
  int code = http.POST(eventJson);
  bool success = false;
  
  if (code > 0) {
    String resp = http.getString();
    Serial.printf("Event upload code=%d resp=%s\n", code, resp.c_str());
    
    if (code >= 200 && code < 300) {
      success = true;
      removeEventFromQueue();
      resetRetryDelay();
      Serial.println("Event successfully uploaded and removed from queue");
    } else {
      Serial.printf("Server error: %d\n", code);
    }
  } else {
    Serial.printf("Network error: %d\n", code);
  }
  
  http.end();
  return success;
}

// ====================================================================================
//  SECTION: RTOS TASK IMPLEMENTATIONS
// ====================================================================================

void TaskInput(void* pvParameters) {
  Serial.println("TaskInput started");
  
  while (true) {
    handleButtons();
    vTaskDelay(pdMS_TO_TICKS(50)); // 50ms polling
  }
}

void TaskControl(void* pvParameters) {
  Serial.println("TaskControl started");
  
  while (true) {
    ControlMsg msg;
    if (xQueueReceive(g_controlQueue, &msg, pdMS_TO_TICKS(100)) == pdTRUE) {
      switch (msg.type) {
        case CTL_START_B:
          startTreatment(0); // BASIC
          break;
        case CTL_START_S:
          startTreatment(1); // STANDARD
          break;
        case CTL_START_P:
          startTreatment(2); // PREMIUM
          break;
        case CTL_STOP:
          stopTreatment();
          break;
      }
    }
    
    // Update timer if active
    if (timerActive) {
      updateTimer();
    }
    
    vTaskDelay(pdMS_TO_TICKS(100));
  }
}

void TaskDisplay(void* pvParameters) {
  Serial.println("TaskDisplay started");
  
  while (true) {
    if (displayNeedsUpdate) {
      updateDisplay();
      displayNeedsUpdate = false;
    }
    
    handleLCDSleep();
    vTaskDelay(pdMS_TO_TICKS(500)); // 500ms refresh rate
  }
}

void TaskNet(void* pvParameters) {
  Serial.println("TaskNet started");
  
  while (true) {
    // Process event queue
    if (WiFi.status() == WL_CONNECTED && !isQueueEmpty()) {
      unsigned long now = millis();
      
      // Check if it's time for next upload attempt
      if (now - lastUploadAttempt >= currentRetryDelay) {
        bool success = processEventQueue();
        lastUploadAttempt = now;
        
        if (!success) {
          int newDelay = calculateRetryDelay();
          Serial.printf("Upload failed, retrying in %d ms (attempt %d)\n", newDelay, retryAttempts);
        }
      }
    }
    
    vTaskDelay(pdMS_TO_TICKS(1000)); // Check every second
  }
}