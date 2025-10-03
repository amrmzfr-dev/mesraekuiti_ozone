// Ozone Machine SIMULATION firmware (no GPIO usage) with real-like uploader
// - Serial UI: b=Basic, s=Standard, p=Premium, hold x for 2s to stop, r=reset
// - EEPROM counters persist across power cycles
// - LittleFS queue, handshake, HTTPS upload (idempotent event_id)

#include <Arduino.h>
#include <EEPROM.h>
#include <ArduinoJson.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include "pins.h"
#include <RTClib.h>

// Relay level fallbacks (if not defined in pins.h)
#ifndef RELAY_ACTIVE_LOW
#define RELAY_ACTIVE_LOW 1
#endif
#ifndef RELAY_ON_LEVEL
#define RELAY_ON_LEVEL (RELAY_ACTIVE_LOW ? LOW : HIGH)
#endif
#ifndef RELAY_OFF_LEVEL
#define RELAY_OFF_LEVEL (RELAY_ACTIVE_LOW ? HIGH : LOW)
#endif

// ============================ Build-time config ==============================
static const char* FIRMWARE_VERSION = "1.0.0-sim";

// Wi-Fi
static const char* WIFI_AP_SSID = "OZONE-CONFIG";
static const char* WIFI_AP_PASS = "mb95z78y";
static const char* WIFI_DEFAULT_SSID = "testtest";
static const char* WIFI_DEFAULT_PASS = "mb95z78y";

// Backend endpoints (must match real firmware)
// For local testing, point to your laptop/server IP (same hotspot network)
// Example: http://192.168.43.100:8000
static const char* BACKEND_BASE = "http://10.49.218.5:8000";
static const char* URL_HANDSHAKE = "/api/handshake/";
static const char* URL_EVENTS    = "/api/device/events/";
static const char* URL_COMMANDS  = "/api/device/";
static const uint32_t HTTPS_TIMEOUT_MS = 5000;
static const bool USE_INSECURE_TLS = true; // set to false when embedding root CA

// Queue
static const char* EVENT_QUEUE_FILE = "/events.jsonl";
static const size_t MAX_QUEUE_SIZE = 4 * 1024 * 1024;
static const uint32_t RETRY_BASE_DELAY_MS = 2000;
static const uint32_t RETRY_MAX_DELAY_MS  = 300000;
static const uint8_t  RETRY_JITTER_PERCENT = 20;

// Command System
static const uint32_t COMMAND_POLL_INTERVAL_MS = 30000; // 30 seconds
static const char* COMMAND_QUEUE_FILE = "/commands.jsonl";
static const size_t MAX_COMMAND_QUEUE_SIZE = 1024 * 1024; // 1MB

// Durations (ms) testing
static const uint32_t DURATION_B_MS = 5000;
static const uint32_t DURATION_S_MS = 10000;
static const uint32_t DURATION_P_MS = 15000;

// ============================== EEPROM layout ================================
static const uint16_t EEPROM_SIZE = 512;
static const uint16_t ADDR_COUNTER_B = 0;
static const uint16_t ADDR_COUNTER_S = 4;
static const uint16_t ADDR_COUNTER_P = 8;
static const uint16_t ADDR_MAGIC     = 12;
static const uint16_t MAGIC_VALUE    = 0x1234;
static const uint16_t ADDR_RESET_COUNTER = 16;
static const uint16_t ADDR_WIFI_SSID = 20;  // 32 bytes
static const uint16_t ADDR_WIFI_PASS = 60;  // 64 bytes
static const uint16_t ADDR_DEVICE_ID = 140; // 64 bytes
static const uint16_t ADDR_TOKEN     = 204; // 128 bytes

// ================================ Types/State ================================
enum class Treatment : uint8_t { Basic=0, Standard=1, Premium=2, None=255 };

enum class CommandType : uint8_t { 
  RESET_COUNTERS=0, CLEAR_MEMORY=1, CLEAR_QUEUE=2, REBOOT_DEVICE=3, 
  UPDATE_SETTINGS=4, GET_STATUS=5, SYNC_TIME=6, UPDATE_FIRMWARE=7, 
  UNKNOWN=255 
};

static uint32_t counterB = 0, counterS = 0, counterP = 0;
static uint32_t resetCounter = 0; // Increments on each reset to ensure unique event IDs
static Treatment active = Treatment::None;
static uint32_t activeDurationMs = 0;
static uint64_t activeStartMs = 0;

static String wifiSsid;
static String wifiPass;
static String deviceId;
static String deviceToken;

static uint32_t currentRetryDelay = RETRY_BASE_DELAY_MS;
static uint32_t lastUploadAttempt = 0;
static uint8_t retryAttempts = 0;

// Command System State
static uint32_t lastCommandPoll = 0;
static uint32_t commandRetryDelay = RETRY_BASE_DELAY_MS;
static uint8_t commandRetryAttempts = 0;

// WiFi Reconnection State
static uint32_t lastReconnectAttempt = 0;
static uint32_t reconnectDelay = 30000; // Start with 30 seconds
static uint8_t reconnectAttempts = 0;
static int32_t lastRSSI = -100; // Track connection quality
static uint32_t lastConnectionCheck = 0;

// Advanced WiFi Statistics
struct WiFiStats {
  uint32_t packetsSent;
  uint32_t packetsLost;
  uint32_t totalLatency;
  uint32_t latencySamples;
  uint32_t minLatency;
  uint32_t maxLatency;
  int32_t minRSSI;
  int32_t maxRSSI;
  uint32_t disconnections;
  uint32_t reconnections;
  uint32_t lastPingTime;
  uint32_t consecutiveFailures;
  float connectionQualityScore;
};

static WiFiStats wifiStats = {0};
static uint32_t lastPingTest = 0;
static uint32_t lastStatsUpdate = 0;

// RTC instance
static RTC_DS3231 g_rtc;

// Button state (edge detection)
static bool btnBLast = false;
static bool btnSLast = false;
static bool btnPLast = false;
static uint32_t btnPHoldStart = 0;

// Kuala Lumpur timezone (UTC+8)
static const long KL_GMT_OFFSET = 8 * 3600;
static const int KL_DST_OFFSET = 0;

static bool syncRTCFromNTP() {
  // Configure SNTP and wait for valid time
  configTime(KL_GMT_OFFSET, KL_DST_OFFSET, "pool.ntp.org", "time.google.com", "time.nist.gov");
  time_t now = 0;
  uint32_t start = millis();
  while ((now = time(nullptr)) < 8 * 3600 && (millis() - start) < 10000) { // wait up to 10s
    delay(250);
  }
  if (now < 8 * 3600) {
    Serial.println("⏱️ NTP: Failed to obtain time");
    return false;
  }
  struct tm tmnow; localtime_r(&now, &tmnow); // local time (KL)
  // Set RTC if available
  if (g_rtc.begin()) {
    DateTime dt(tmnow.tm_year + 1900, tmnow.tm_mon + 1, tmnow.tm_mday, tmnow.tm_hour, tmnow.tm_min, tmnow.tm_sec);
    g_rtc.adjust(dt);
    Serial.print("⏱️ RTC synced: "); Serial.println(dt.timestamp());
    return true;
  }
  return false;
}

// ============================== Helpers ======================================
static void eepromWriteString(uint16_t addr, uint16_t maxLen, const String& s) {
  uint16_t n = min<uint16_t>((uint16_t)s.length(), (uint16_t)(maxLen - 1));
  for (uint16_t i=0;i<n;i++) EEPROM.write(addr+i, (uint8_t)s[i]);
  EEPROM.write(addr+n, 0);
}

static String eepromReadString(uint16_t addr, uint16_t maxLen) {
  String s; s.reserve(maxLen);
  for (uint16_t i=0;i<maxLen;i++) { char c=(char)EEPROM.read(addr+i); if (c==0 || c== (char)0xFF) break; s += c; }
  return s;
}

static void saveCounters() {
  EEPROM.put(ADDR_COUNTER_B, counterB);
  EEPROM.put(ADDR_COUNTER_S, counterS);
  EEPROM.put(ADDR_COUNTER_P, counterP);
  EEPROM.put(ADDR_RESET_COUNTER, resetCounter);
  EEPROM.commit();
}

static void loadCounters() {
  uint16_t magic=0; EEPROM.get(ADDR_MAGIC, magic);
  if (magic==MAGIC_VALUE) {
    EEPROM.get(ADDR_COUNTER_B, counterB);
    EEPROM.get(ADDR_COUNTER_S, counterS);
    EEPROM.get(ADDR_COUNTER_P, counterP);
    EEPROM.get(ADDR_RESET_COUNTER, resetCounter);
  } else {
    counterB=counterS=counterP=0;
    resetCounter=0;
    EEPROM.put(ADDR_COUNTER_B, counterB);
    EEPROM.put(ADDR_COUNTER_S, counterS);
    EEPROM.put(ADDR_COUNTER_P, counterP);
    EEPROM.put(ADDR_RESET_COUNTER, resetCounter);
    EEPROM.put(ADDR_MAGIC, MAGIC_VALUE);
    EEPROM.commit();
  }
}

static void loadWifiCreds() {
  wifiSsid = eepromReadString(ADDR_WIFI_SSID, 32);
  wifiPass = eepromReadString(ADDR_WIFI_PASS, 64);
  if (wifiSsid.length()==0) wifiSsid = WIFI_DEFAULT_SSID;
  if (wifiPass.length()==0) wifiPass = WIFI_DEFAULT_PASS;
}

static void saveWifiCreds(const String& ssid, const String& pass) {
  eepromWriteString(ADDR_WIFI_SSID, 32, ssid);
  eepromWriteString(ADDR_WIFI_PASS, 64, pass);
  EEPROM.commit();
  wifiSsid = ssid; wifiPass = pass;
}

static void loadIdentity() {
  deviceId = eepromReadString(ADDR_DEVICE_ID, 64);
  deviceToken = eepromReadString(ADDR_TOKEN, 128);
}

static void saveIdentity(const String& id, const String& token) {
  eepromWriteString(ADDR_DEVICE_ID, 64, id);
  eepromWriteString(ADDR_TOKEN, 128, token);
  EEPROM.commit();
  deviceId = id; deviceToken = token;
}

static const char* treatmentName(Treatment t) {
  switch (t) { case Treatment::Basic: return "BASIC"; case Treatment::Standard: return "STANDARD"; case Treatment::Premium: return "PREMIUM"; default: return "UNKNOWN"; }
}

static const char* commandTypeName(CommandType t) {
  switch (t) { 
    case CommandType::RESET_COUNTERS: return "RESET_COUNTERS";
    case CommandType::CLEAR_MEMORY: return "CLEAR_MEMORY";
    case CommandType::CLEAR_QUEUE: return "CLEAR_QUEUE";
    case CommandType::REBOOT_DEVICE: return "REBOOT_DEVICE";
    case CommandType::UPDATE_SETTINGS: return "UPDATE_SETTINGS";
    case CommandType::GET_STATUS: return "GET_STATUS";
    case CommandType::SYNC_TIME: return "SYNC_TIME";
    case CommandType::UPDATE_FIRMWARE: return "UPDATE_FIRMWARE";
    default: return "UNKNOWN";
  }
}

static CommandType parseCommandType(const String& typeStr) {
  if (typeStr == "RESET_COUNTERS") return CommandType::RESET_COUNTERS;
  if (typeStr == "CLEAR_MEMORY") return CommandType::CLEAR_MEMORY;
  if (typeStr == "CLEAR_QUEUE") return CommandType::CLEAR_QUEUE;
  if (typeStr == "REBOOT_DEVICE") return CommandType::REBOOT_DEVICE;
  if (typeStr == "UPDATE_SETTINGS") return CommandType::UPDATE_SETTINGS;
  if (typeStr == "GET_STATUS") return CommandType::GET_STATUS;
  if (typeStr == "SYNC_TIME") return CommandType::SYNC_TIME;
  if (typeStr == "UPDATE_FIRMWARE") return CommandType::UPDATE_FIRMWARE;
  return CommandType::UNKNOWN;
}

static void drawMain() {
  Serial.println();
  Serial.println("================ OZONE MACHINE =================");
  Serial.println("      OZONE MACHINE      ");
  char buf[32]; snprintf(buf,sizeof(buf),"%04lu %04lu %04lu",(unsigned long)counterB,(unsigned long)counterS,(unsigned long)counterP);
  Serial.println(buf);
  Serial.println("  B     S     P  ");
  Serial.println("BASIC  STD  PREM");
  Serial.println("b=basic s=standard p=premium  x(hold)=stop  r=reset  t=test network  o=queue status  c=poll commands  q=clear command queue  d=debug command queue  j=json test  w=wifi diagnostics  n=reconnect wifi  m=manual reconnect  s=advanced stats");
}

static void drawTimer() {
  Serial.println();
  Serial.println("================ OZONE MACHINE =================");
  Serial.println("      OZONE MACHINE      ");
  const char* name = (active==Treatment::Basic)?"BASIC TREATMENT":(active==Treatment::Standard)?"STANDARD TREATMENT":"PREMIUM TREATMENT";
  Serial.println(name);
  uint32_t elapsed = (uint32_t)(millis()-activeStartMs);
  uint32_t remain = (elapsed>=activeDurationMs)?0:(activeDurationMs-elapsed);
  uint32_t mm = remain/1000/60; uint32_t ss = (remain/1000)%60;
  char tbuf[16]; snprintf(tbuf,sizeof(tbuf),"%02lu:%02lu",(unsigned long)mm,(unsigned long)ss);
  Serial.println(tbuf);
  Serial.println("hold x for 2s to stop");
}

// ============================== Queue (LittleFS) =============================
static bool ensureQueue() {
  if (!LittleFS.begin(true)) { Serial.println("FS mount failed"); return false; }
  if (!LittleFS.exists(EVENT_QUEUE_FILE)) { File f = LittleFS.open(EVENT_QUEUE_FILE, "w"); if (!f) return false; f.close(); }
  return true;
}

static size_t queueSize() { File f = LittleFS.open(EVENT_QUEUE_FILE, "r"); if (!f) return 0; size_t s=f.size(); f.close(); return s; }

static bool appendEventToQueue(const String& line) {
  if (!ensureQueue()) return false; if (queueSize() > MAX_QUEUE_SIZE) return false; File f = LittleFS.open(EVENT_QUEUE_FILE, "a"); if (!f) return false; f.println(line); f.close(); return true;
}

static String readNextEvent() { if (!ensureQueue()) return String(); File f=LittleFS.open(EVENT_QUEUE_FILE, "r"); if(!f) return String(); String line=f.readStringUntil('\n'); f.close(); return line; }

static bool popEvent() {
  if (!ensureQueue()) return false; File in=LittleFS.open(EVENT_QUEUE_FILE, "r"); if(!in) return false; String content=""; (void)in.readStringUntil('\n'); while(in.available()){ content += in.readStringUntil('\n'); content += "\n"; } in.close(); File out=LittleFS.open(EVENT_QUEUE_FILE, "w"); if(!out) return false; out.print(content); out.close(); return true;
}

// ============================== Command Queue (LittleFS) =============================
static bool ensureCommandQueue() {
  if (!LittleFS.begin(true)) { Serial.println("Command FS mount failed"); return false; }
  if (!LittleFS.exists(COMMAND_QUEUE_FILE)) { File f = LittleFS.open(COMMAND_QUEUE_FILE, "w"); if (!f) return false; f.close(); }
  return true;
}

static size_t commandQueueSize() { 
  File f = LittleFS.open(COMMAND_QUEUE_FILE, "r"); 
  if (!f) return 0; 
  size_t s = f.size(); 
  f.close(); 
  return s; 
}

static bool appendCommandToQueue(const String& line) {
  if (!ensureCommandQueue()) return false; 
  if (commandQueueSize() > MAX_COMMAND_QUEUE_SIZE) return false; 
  File f = LittleFS.open(COMMAND_QUEUE_FILE, "a"); 
  if (!f) return false; 
  f.println(line); 
  f.flush(); // Ensure data is written to flash immediately
  f.close(); 
  return true;
}

static String readNextCommand() { 
  if (!ensureCommandQueue()) return String(); 
  File f = LittleFS.open(COMMAND_QUEUE_FILE, "r"); 
  if (!f) return String(); 
  String line = f.readStringUntil('\n'); 
  f.close(); 
  return line; 
}

static bool popCommand() {
  if (!ensureCommandQueue()) return false; 
  File in = LittleFS.open(COMMAND_QUEUE_FILE, "r"); 
  if (!in) return false; 
  String content = ""; 
  (void)in.readStringUntil('\n'); 
  while (in.available()) { 
    content += in.readStringUntil('\n'); 
    content += "\n"; 
  } 
  in.close(); 
  File out = LittleFS.open(COMMAND_QUEUE_FILE, "w"); 
  if (!out) return false; 
  out.print(content); 
  out.flush(); // Ensure data is written to flash immediately
  out.close(); 
  return true;
}

// ============================== Network =====================================
static bool performHandshake() {
  // Check WiFi connection first
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("❌ HANDSHAKE: WiFi not connected");
    return false;
  }
  
  HTTPClient http; 
  String url = String(BACKEND_BASE) + URL_HANDSHAKE;
  
  Serial.print("🔐 HANDSHAKE: Connecting to ");
  Serial.println(url);
  
  if (!http.begin(url)) {
    Serial.println("❌ HANDSHAKE: Failed to begin HTTP connection");
    return false; 
  }
  
  http.setTimeout(HTTPS_TIMEOUT_MS); 
  http.addHeader("Content-Type","application/json");
  
  StaticJsonDocument<256> body; 
  body["mac"]=WiFi.macAddress(); 
  body["firmware"]=FIRMWARE_VERSION; 
  String payload; 
  serializeJson(body,payload);
  
  Serial.print("📤 HANDSHAKE: Sending MAC ");
  Serial.println(WiFi.macAddress());
  
  int code = http.POST(payload);
  Serial.print("📥 HANDSHAKE: Response code ");
  Serial.println(code);
  
  if (code>0) { 
    String resp=http.getString(); 
    Serial.print("📥 HANDSHAKE: Response body: ");
    Serial.println(resp);
    
    StaticJsonDocument<512> doc; 
    if (deserializeJson(doc,resp)==DeserializationError::Ok) { 
      String id=doc["device_id"].as<String>(); 
      String tok=doc["token"].as<String>(); 
      bool assigned = doc.containsKey("assigned") ? doc["assigned"].as<bool>() : false;
      if (id.length()>0 && tok.length()>0) { 
        saveIdentity(id,tok); 
        Serial.print("✅ HANDSHAKE: Device registered - ID: ");
        Serial.print(id);
        Serial.print(", Token: ");
        Serial.println(tok.substring(0, 8) + "...");
        Serial.print("🗂️ HANDSHAKE: Assigned: ");
        Serial.println(assigned ? "true" : "false");
        http.end(); 
        return true; 
  } else {
        Serial.println("❌ HANDSHAKE: Invalid response - missing device_id or token");
      }
  } else {
      Serial.println("❌ HANDSHAKE: Failed to parse JSON response");
    }
  } else {
    Serial.print("❌ HANDSHAKE: HTTP error ");
    Serial.println(code);
    
    // Trigger reconnection on handshake failure
    if (code == -1 || code == -2 || code == -3) { // Connection errors
      Serial.println("🔄 HANDSHAKE: Connection error detected, triggering WiFi reconnection");
      lastReconnectAttempt = 0; // Force immediate reconnection attempt
    }
  }
  http.end(); 
  return false;
}

static String makeIsoNow() {
  // Return Malaysian local time as "YYYY-MM-DD HH:MM:SS" (no T/Z letters)
  char ts[32];
  if (g_rtc.begin()) {
    DateTime now = g_rtc.now();
    snprintf(ts, sizeof(ts), "%04d-%02d-%02d %02d:%02d:%02d",
             now.year(), now.month(), now.day(), now.hour(), now.minute(), now.second());
    return String(ts);
  }
  time_t tnow = time(nullptr);
  if (tnow > 0) {
    struct tm tmnow; localtime_r(&tnow, &tmnow);
    snprintf(ts, sizeof(ts), "%04d-%02d-%02d %02d:%02d:%02d",
             tmnow.tm_year + 1900, tmnow.tm_mon + 1, tmnow.tm_mday,
             tmnow.tm_hour, tmnow.tm_min, tmnow.tm_sec);
    return String(ts);
  }
  // Fallback approximate time
  uint32_t sec = millis()/1000; uint32_t m=sec/60; uint32_t h=m/60; uint32_t d=h/24;
  snprintf(ts,sizeof(ts),"2025-%02u-%02u %02u:%02u:%02u", (d/30)%12+1, d%30+1, h%24, m%60, sec%60);
  return String(ts);
}

static String generateEventId(Treatment t, uint32_t counterVal) {
  char buf[80]; 
  const char* treatmentPrefix = (t == Treatment::Basic) ? "B" : (t == Treatment::Standard) ? "S" : "P";
  
  // Create unique event ID using: device_id + treatment + reset_counter + timestamp + counter
  uint32_t timestamp = millis() / 1000; // Seconds since boot
  snprintf(buf,sizeof(buf),"%s-%s%03lu%08lu%06lu", 
    deviceId.length()?deviceId.c_str():"esp32-sim", 
    treatmentPrefix, 
    (unsigned long)resetCounter,  // 3 digits for reset counter (0-999)
    (unsigned long)timestamp,     // 8 digits for timestamp
    (unsigned long)counterVal     // 6 digits for counter (0-999999)
  );
  return String(buf);
}

static bool uploadEventJson(const String& jsonLine) {
  // Check if we have device credentials
  if (deviceToken.length() == 0) {
    Serial.println("❌ UPLOAD: No device token available - handshake required");
    return false;
  }
  
  // Check WiFi connection
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("❌ UPLOAD: WiFi not connected");
    return false;
  }
  
  HTTPClient http; 
  String url = String(BACKEND_BASE) + URL_EVENTS;
  
  Serial.print("🌐 UPLOAD: Connecting to ");
  Serial.print(url);
  Serial.print(" | WiFi IP: ");
  Serial.println(WiFi.localIP());
  
  if (!http.begin(url)) { 
    Serial.println("❌ UPLOAD: Failed to begin HTTP connection");
    return false; 
  }
  
  http.setTimeout(HTTPS_TIMEOUT_MS);
  http.addHeader("Content-Type","application/json"); 
  http.addHeader("Authorization", String("Bearer ") + deviceToken);
  
  Serial.print("🔄 UPLOAD: Attempting to upload event... ");
  int code = http.POST(jsonLine);
  bool ok = (code>=200 && code<300);
  
  if (ok) { 
    Serial.print("✅ SUCCESS (HTTP ");
    Serial.print(code);
    Serial.println(")");
  } else { 
    Serial.print("❌ FAILED (HTTP ");
    Serial.print(code);
    Serial.print(") - ");
    if (code == -1) {
      Serial.println("Connection failed - check backend URL and network");
    } else if (code == -2) {
      Serial.println("Connection timeout");
    } else if (code == -3) {
      Serial.println("Connection refused");
    } else if (code == -4) {
      Serial.println("Connection reset");
    } else if (code == -5) {
      Serial.println("Connection aborted");
    } else if (code == -6) {
      Serial.println("Connection closed");
    } else if (code == -7) {
      Serial.println("Connection lost");
    } else if (code == -8) {
      Serial.println("Connection timeout");
    } else if (code == -9) {
      Serial.println("Connection failed");
    } else if (code == -10) {
      Serial.println("Connection failed");
    } else if (code == -11) {
      Serial.println("Connection failed");
    } else {
      Serial.print("Unknown error: ");
      Serial.println(code);
    }
    
    // Trigger reconnection on upload failure
    if (code == -1 || code == -2 || code == -3) { // Connection errors
      Serial.println("🔄 UPLOAD: Connection error detected, triggering WiFi reconnection");
      lastReconnectAttempt = 0; // Force immediate reconnection attempt
    }
  }
  http.end(); 
  return ok;
}

static void resetBackoff() { currentRetryDelay = RETRY_BASE_DELAY_MS; retryAttempts = 0; }
static uint32_t nextBackoffMs() { uint32_t d=currentRetryDelay; currentRetryDelay=min<uint32_t>(currentRetryDelay*2, RETRY_MAX_DELAY_MS); retryAttempts++; uint32_t j=(d*RETRY_JITTER_PERCENT)/100; int32_t off=random(-(int32_t)j,(int32_t)j+1); int64_t res=(int64_t)d+off; if(res<1000) res=1000; return (uint32_t)res; }

static void testNetworkConnectivity() {
  Serial.println("🌐 NETWORK: Testing connectivity...");
  Serial.print("📡 WiFi Status: ");
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Connected | IP: ");
    Serial.print(WiFi.localIP());
    Serial.print(" | RSSI: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
    
    // Test basic connectivity
    HTTPClient http;
    String testUrl = String(BACKEND_BASE) + "/";
    Serial.print("🔍 Testing connection to ");
    Serial.println(testUrl);
    
    if (http.begin(testUrl)) {
      http.setTimeout(3000); // Shorter timeout for test
      int code = http.GET();
      Serial.print("📊 Test response: HTTP ");
      Serial.println(code);
      http.end();
    } else {
      Serial.println("❌ Test failed: Could not begin connection");
    }
  } else {
    Serial.println("Disconnected");
  }
}

// ============================== WiFi Reconnection =====================================
static void resetReconnectionBackoff() {
  reconnectDelay = 30000; // Reset to 30 seconds
  reconnectAttempts = 0;
  Serial.println("🔄 WIFI: Reconnection backoff reset");
}

static uint32_t nextReconnectionDelay() {
  uint32_t delay = reconnectDelay;
  reconnectDelay = min(reconnectDelay * 2, 300000); // Max 5 minutes
  reconnectAttempts++;
  
  // Add jitter to prevent thundering herd
  uint32_t jitter = (delay * 20) / 100; // ±20% jitter
  int32_t offset = random(-(int32_t)jitter, (int32_t)jitter + 1);
  int64_t result = (int64_t)delay + offset;
  
  if (result < 10000) result = 10000; // Minimum 10 seconds
  return (uint32_t)result;
}

static bool attemptWiFiReconnection() {
  Serial.print("🔄 WIFI: Attempting reconnection (attempt #");
  Serial.print(reconnectAttempts + 1);
  Serial.print(") to '");
  Serial.print(wifiSsid);
  Serial.println("'");
  
  // Disconnect first to ensure clean state
  WiFi.disconnect();
  delay(1000);
  
  // Attempt reconnection
  WiFi.begin(wifiSsid.c_str(), wifiPass.c_str());
  
  uint32_t start = millis();
  uint32_t timeout = min(15000, 5000 + (reconnectAttempts * 2000)); // Longer timeout for retries
  
  while (WiFi.status() != WL_CONNECTED && millis() - start < timeout) {
    delay(250);
    Serial.print('.');
    
    if (WiFi.status() == WL_CONNECT_FAILED) {
      Serial.println("\n❌ WIFI: Connection failed - check credentials");
      break;
    }
  }
  Serial.println();
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("✅ WIFI: Reconnection successful! IP: ");
    Serial.println(WiFi.localIP());
    Serial.print("📡 WIFI: RSSI: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
    
    // Reset backoff on successful connection
    resetReconnectionBackoff();
    lastRSSI = WiFi.RSSI();
    wifiStats.reconnections++; // Track reconnection events
    
    // Sync RTC from NTP
    if (syncRTCFromNTP()) {
      Serial.println("⏰ NTP: RTC synchronized after reconnection");
    }
    
    return true;
  } else {
    Serial.print("❌ WIFI: Reconnection failed (attempt #");
    Serial.print(reconnectAttempts + 1);
    Serial.println(")");
    
    // Update backoff delay
    reconnectDelay = nextReconnectionDelay();
    Serial.print("⏰ WIFI: Next reconnection attempt in ");
    Serial.print(reconnectDelay / 1000);
    Serial.println(" seconds");
    
    return false;
  }
}

static void monitorConnectionQuality() {
  if (WiFi.status() == WL_CONNECTED) {
    int32_t currentRSSI = WiFi.RSSI();
    
    // Update RSSI statistics
    if (wifiStats.minRSSI == 0 || currentRSSI < wifiStats.minRSSI) {
      wifiStats.minRSSI = currentRSSI;
    }
    if (currentRSSI > wifiStats.maxRSSI) {
      wifiStats.maxRSSI = currentRSSI;
    }
    
    // Check for significant signal degradation
    if (currentRSSI < -80 && lastRSSI > -70) {
      Serial.print("⚠️ WIFI: Signal degraded - RSSI: ");
      Serial.print(currentRSSI);
      Serial.println(" dBm");
    }
    
    // Check for connection loss
    if (currentRSSI < -90) {
      Serial.println("⚠️ WIFI: Very weak signal, connection may be unstable");
    }
    
    lastRSSI = currentRSSI;
  }
}

// ============================== Advanced WiFi Diagnostics =====================================
static uint32_t performPingTest() {
  if (WiFi.status() != WL_CONNECTED) {
    return 0; // No connection
  }
  
  HTTPClient http;
  String testUrl = String(BACKEND_BASE) + "/";
  
  uint32_t startTime = millis();
  if (http.begin(testUrl)) {
    http.setTimeout(2000); // 2 second timeout for ping
    int code = http.GET();
    uint32_t latency = millis() - startTime;
    http.end();
    
    wifiStats.packetsSent++;
    
    if (code > 0) {
      // Successful ping
      wifiStats.totalLatency += latency;
      wifiStats.latencySamples++;
      
      if (wifiStats.minLatency == 0 || latency < wifiStats.minLatency) {
        wifiStats.minLatency = latency;
      }
      if (latency > wifiStats.maxLatency) {
        wifiStats.maxLatency = latency;
      }
      
      wifiStats.consecutiveFailures = 0;
      wifiStats.lastPingTime = latency;
      
      return latency;
    } else {
      // Failed ping
      wifiStats.packetsLost++;
      wifiStats.consecutiveFailures++;
      return 0;
    }
  } else {
    wifiStats.packetsLost++;
    wifiStats.consecutiveFailures++;
    return 0;
  }
}

static void updateConnectionQualityScore() {
  if (wifiStats.packetsSent == 0) {
    wifiStats.connectionQualityScore = 0.0;
    return;
  }
  
  float packetLossRate = (float)wifiStats.packetsLost / wifiStats.packetsSent;
  float avgLatency = wifiStats.latencySamples > 0 ? 
    (float)wifiStats.totalLatency / wifiStats.latencySamples : 0.0;
  
  // Calculate quality score (0-100)
  float latencyScore = 0.0;
  if (avgLatency > 0) {
    if (avgLatency < 50) latencyScore = 100.0;
    else if (avgLatency < 100) latencyScore = 80.0;
    else if (avgLatency < 200) latencyScore = 60.0;
    else if (avgLatency < 500) latencyScore = 40.0;
    else latencyScore = 20.0;
  }
  
  float packetLossScore = (1.0 - packetLossRate) * 100.0;
  float rssiScore = 0.0;
  
  if (lastRSSI > -50) rssiScore = 100.0;
  else if (lastRSSI > -60) rssiScore = 90.0;
  else if (lastRSSI > -70) rssiScore = 80.0;
  else if (lastRSSI > -80) rssiScore = 60.0;
  else if (lastRSSI > -90) rssiScore = 30.0;
  else rssiScore = 10.0;
  
  // Weighted average: 40% packet loss, 40% latency, 20% RSSI
  wifiStats.connectionQualityScore = (packetLossScore * 0.4) + (latencyScore * 0.4) + (rssiScore * 0.2);
}

static void printAdvancedWiFiStats() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("📊 WIFI STATS: Not connected");
    return;
  }
  
  Serial.println("📊 WIFI STATS: Advanced Diagnostics");
  Serial.println("=====================================");
  
  // Connection Info
  Serial.print("📡 Status: Connected | IP: ");
  Serial.print(WiFi.localIP());
  Serial.print(" | RSSI: ");
  Serial.print(WiFi.RSSI());
  Serial.println(" dBm");
  
  // Packet Statistics
  if (wifiStats.packetsSent > 0) {
    float packetLossRate = (float)wifiStats.packetsLost / wifiStats.packetsSent * 100.0;
    Serial.print("📦 Packets: ");
    Serial.print(wifiStats.packetsSent - wifiStats.packetsLost);
    Serial.print("/");
    Serial.print(wifiStats.packetsSent);
    Serial.print(" (");
    Serial.print(100.0 - packetLossRate, 1);
    Serial.print("% success) | Loss: ");
    Serial.print(packetLossRate, 1);
    Serial.println("%");
  } else {
    Serial.println("📦 Packets: No data available");
  }
  
  // Latency Statistics
  if (wifiStats.latencySamples > 0) {
    float avgLatency = (float)wifiStats.totalLatency / wifiStats.latencySamples;
    Serial.print("⏱️ Latency: ");
    Serial.print(avgLatency, 0);
    Serial.print("ms avg | ");
    Serial.print(wifiStats.minLatency);
    Serial.print("-");
    Serial.print(wifiStats.maxLatency);
    Serial.println("ms range");
  } else {
    Serial.println("⏱️ Latency: No data available");
  }
  
  // RSSI Statistics
  if (wifiStats.minRSSI != 0) {
    Serial.print("📶 RSSI Range: ");
    Serial.print(wifiStats.minRSSI);
    Serial.print(" to ");
    Serial.print(wifiStats.maxRSSI);
    Serial.println(" dBm");
  }
  
  // Connection Events
  Serial.print("🔄 Events: ");
  Serial.print(wifiStats.disconnections);
  Serial.print(" disconnects, ");
  Serial.print(wifiStats.reconnections);
  Serial.println(" reconnects");
  
  // Quality Score
  Serial.print("⭐ Quality Score: ");
  Serial.print(wifiStats.connectionQualityScore, 1);
  Serial.print("/100 (");
  if (wifiStats.connectionQualityScore >= 90) Serial.println("Excellent)");
  else if (wifiStats.connectionQualityScore >= 70) Serial.println("Good)");
  else if (wifiStats.connectionQualityScore >= 50) Serial.println("Fair)");
  else if (wifiStats.connectionQualityScore >= 30) Serial.println("Poor)");
  else Serial.println("Critical)");
  
  // Warnings
  if (wifiStats.consecutiveFailures > 3) {
    Serial.print("⚠️ WARNING: ");
    Serial.print(wifiStats.consecutiveFailures);
    Serial.println(" consecutive ping failures");
  }
  
  if (wifiStats.connectionQualityScore < 50) {
    Serial.println("⚠️ WARNING: Poor connection quality detected");
  }
  
  Serial.println("=====================================");
}

// ============================== Command System =====================================
static bool pollCommands() {
  // Check WiFi connection first
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("❌ COMMAND: WiFi not connected");
    return false;
  }
  
  // Check if we have device credentials
  if (deviceToken.length() == 0) {
    Serial.println("❌ COMMAND: No device token");
    return false;
  }
  
  HTTPClient http; 
  String url = String(BACKEND_BASE) + URL_COMMANDS + deviceId + "/commands/";
  
  Serial.print("📡 COMMAND: Polling for commands from ");
  Serial.println(url);
  
  // Add connection reuse and better error handling
  http.setReuse(true);
  http.setTimeout(HTTPS_TIMEOUT_MS);
  
  if (!http.begin(url)) {
    Serial.println("❌ COMMAND: Failed to begin HTTP connection");
    return false; 
  }
  
  http.addHeader("Authorization", String("Bearer ") + deviceToken);
  http.addHeader("Connection", "keep-alive");
  
  int code = http.GET();
  
  if (code == 401) {
    Serial.println("🔐 COMMAND: Unauthorized (401). Re-running handshake...");
    http.end();
    if (performHandshake()) {
      // Retry once with refreshed credentials
      if (!http.begin(url)) { Serial.println("❌ COMMAND: Re-begin failed after handshake"); return false; }
      http.addHeader("Authorization", String("Bearer ") + deviceToken);
      http.addHeader("Connection", "keep-alive");
      code = http.GET();
    }
  }
  
  if (code >= 200 && code < 300) { 
    String resp = http.getString(); 
    Serial.print("📥 COMMAND: Response code ");
    Serial.print(code);
    Serial.print(" | Body: ");
    Serial.println(resp);
    
    StaticJsonDocument<1024> doc; 
    if (deserializeJson(doc, resp) == DeserializationError::Ok) { 
      if (doc.containsKey("commands") && doc["commands"].is<JsonArray>()) {
        JsonArray commands = doc["commands"];
        if (commands.size() > 0) {
          Serial.print("📋 COMMAND: Received ");
          Serial.print(commands.size());
          Serial.println(" commands");
          
          for (JsonObject cmd : commands) {
            // Use the correct field name as specified by backend
            String commandId = cmd["command_id"].as<String>();
            
            String commandType = cmd["command_type"].as<String>();
            String payload = cmd["payload"].as<String>();
            
            Serial.print("🎯 COMMAND: Processing ");
            Serial.print(commandType);
            Serial.print(" (ID: '");
            Serial.print(commandId);
            Serial.println("')");
            
            // Debug: Show raw command from backend
            Serial.print("🔍 COMMAND: Raw backend command - ID length: ");
            Serial.print(commandId.length());
            Serial.print(", Type: '");
            Serial.print(commandType);
            Serial.print("', Payload: '");
            Serial.print(payload);
            Serial.println("'");
            
            // Validate command ID
            if (commandId.length() == 0 || commandId == "null") {
              Serial.println("❌ COMMAND: Invalid command ID (empty or 'null' string) - skipping command");
              continue;
            }
            
            // Queue command for execution
            StaticJsonDocument<512> cmdDoc;
            cmdDoc["id"] = commandId;
            cmdDoc["type"] = commandType;
            cmdDoc["payload"] = payload;
            cmdDoc["timestamp"] = millis();
            
            String cmdLine;
            serializeJson(cmdDoc, cmdLine);
            
            // Debug: Show what we're storing
            Serial.print("💾 COMMAND: Storing to queue: ");
            Serial.println(cmdLine);
            
            if (appendCommandToQueue(cmdLine)) {
              Serial.println("✅ COMMAND: Queued for execution");
  } else {
              Serial.println("❌ COMMAND: Failed to queue");
            }
          }
        } else {
          Serial.println("📭 COMMAND: No pending commands");
        }
      }
  } else {
      Serial.println("❌ COMMAND: Failed to parse JSON response");
    }
    http.end();
    return true;
  } else {
    Serial.print("❌ COMMAND: HTTP error ");
    Serial.print(code);
    if (code == -1) {
      Serial.println(" - Connection failed (network issue)");
      
      // Trigger reconnection on command polling failure
      Serial.println("🔄 COMMAND: Connection error detected, triggering WiFi reconnection");
      lastReconnectAttempt = 0; // Force immediate reconnection attempt
    } else {
      Serial.println();
    }
  }
  http.end(); 
  return false;
}

static bool reportCommandResult(const String& commandId, bool success, const String& message = "") {
  // Check WiFi connection first
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("❌ COMMAND: WiFi not connected for result reporting");
    return false;
  }
  
  // Check if we have device credentials
  if (deviceToken.length() == 0) {
    Serial.println("❌ COMMAND: No device token for result reporting");
    return false;
  }
  
  HTTPClient http; 
  String url = String(BACKEND_BASE) + URL_COMMANDS + deviceId + "/commands/" + commandId + "/";
  
  Serial.print("🌐 COMMAND: Reporting to URL: ");
  Serial.println(url);
  
  if (!http.begin(url)) {
    Serial.println("❌ COMMAND: Failed to begin HTTP connection for result");
    return false; 
  }
  
  http.setTimeout(HTTPS_TIMEOUT_MS); 
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", String("Bearer ") + deviceToken);
  
  StaticJsonDocument<512> body; 
  body["success"] = success;
  body["message"] = message;
  body["timestamp"] = millis();
  
  // Add current counter state for backend synchronization
  JsonObject counters = body.createNestedObject("current_counters");
  counters["basic"] = counterB;
  counters["standard"] = counterS;
  counters["premium"] = counterP;
  
  String payload; 
  serializeJson(body, payload);
  
  Serial.print("📤 COMMAND: Reporting result for ");
  Serial.print(commandId);
  Serial.print(" - ");
  Serial.println(success ? "SUCCESS" : "FAILED");
  Serial.print("📤 COMMAND: Payload: ");
  Serial.println(payload);
  Serial.print("📊 COMMAND: Current counters - B:");
  Serial.print(counterB);
  Serial.print(" S:");
  Serial.print(counterS);
  Serial.print(" P:");
  Serial.println(counterP);
  
  int code = http.POST(payload);

  if (code == 401) {
    Serial.println("🔐 COMMAND: Unauthorized (401). Re-running handshake and retrying result report...");
    http.end();
    if (performHandshake()) {
      if (!http.begin(url)) { Serial.println("❌ COMMAND: Re-begin failed after handshake (result)"); return false; }
      http.setTimeout(HTTPS_TIMEOUT_MS);
      http.addHeader("Content-Type", "application/json");
      http.addHeader("Authorization", String("Bearer ") + deviceToken);
      code = http.POST(payload);
    }
  }
  
  if (code >= 200 && code < 300) { 
    Serial.println("✅ COMMAND: Result reported successfully");
    http.end(); 
    return true; 
  } else {
    Serial.print("❌ COMMAND: Failed to report result - HTTP ");
    Serial.print(code);
    Serial.print(" | Response: ");
    Serial.println(http.getString());
  }
  http.end(); 
  return false;
}

static bool executeCommand(const String& commandId, CommandType type, const String& payload) {
  Serial.print("⚡ COMMAND: Executing ");
  Serial.print(commandTypeName(type));
  Serial.print(" (ID: ");
  Serial.print(commandId);
  Serial.println(")");
  
  bool success = false;
  String message = "";
  
  switch (type) {
    case CommandType::RESET_COUNTERS:
      counterB = counterS = counterP = 0;
      resetCounter++; // Increment reset counter for unique event IDs
      saveCounters();
      drawMain();
      success = true;
      message = "Counters reset to 0, reset counter: " + String(resetCounter);
      Serial.print("🔄 COMMAND: Counters reset successfully, reset counter: ");
      Serial.println(resetCounter);
      break;
      
    case CommandType::CLEAR_MEMORY:
      // Clear EEPROM (except device credentials)
      for (int i = 0; i < EEPROM_SIZE; i++) {
        if (i < ADDR_WIFI_SSID || i >= ADDR_WIFI_SSID + 32) {
          EEPROM.write(i, 0xFF);
        }
      }
      EEPROM.commit();
      success = true;
      message = "Memory cleared (except WiFi credentials)";
      Serial.println("🗑️ COMMAND: Memory cleared successfully");
      break;
      
    case CommandType::CLEAR_QUEUE:
      if (LittleFS.begin(true)) {
        if (LittleFS.exists(EVENT_QUEUE_FILE)) {
          LittleFS.remove(EVENT_QUEUE_FILE);
        }
        if (LittleFS.exists(COMMAND_QUEUE_FILE)) {
          LittleFS.remove(COMMAND_QUEUE_FILE);
        }
      }
      success = true;
      message = "Event and command queues cleared";
      Serial.println("🗑️ COMMAND: Queues cleared successfully");
      break;
      
    case CommandType::REBOOT_DEVICE:
      success = true;
      message = "Device will reboot in 3 seconds";
      Serial.println("🔄 COMMAND: Device rebooting...");
      delay(3000);
      ESP.restart();
      break;
      
    case CommandType::GET_STATUS:
      success = true;
      message = "Status: B=" + String(counterB) + " S=" + String(counterS) + " P=" + String(counterP);
      Serial.println("📊 COMMAND: Status retrieved");
      break;
      
    case CommandType::SYNC_TIME:
      // For simulation, just acknowledge
      success = true;
      message = "Time sync acknowledged";
      Serial.println("⏰ COMMAND: Time sync acknowledged");
      break;
      
    case CommandType::UPDATE_SETTINGS:
      success = true;
      message = "Settings update acknowledged";
      Serial.println("⚙️ COMMAND: Settings update acknowledged");
      break;
      
    case CommandType::UPDATE_FIRMWARE:
      success = false;
      message = "Firmware update not supported in simulation";
      Serial.println("❌ COMMAND: Firmware update not supported");
      break;
      
    default:
      success = false;
      message = "Unknown command type";
      Serial.println("❌ COMMAND: Unknown command type");
      break;
  }
  
  return reportCommandResult(commandId, success, message);
}

static void processCommandQueue() {
  size_t cmdSize = commandQueueSize();
  if (cmdSize > 0) {
    Serial.print("📋 COMMAND: Processing command queue (");
    Serial.print(cmdSize);
    Serial.println(" bytes)");
    
    String cmdLine = readNextCommand();
    if (cmdLine.length() > 0) {
      Serial.print("📝 COMMAND: Raw command: ");
      Serial.println(cmdLine);
      
      StaticJsonDocument<512> cmdDoc;
      if (deserializeJson(cmdDoc, cmdLine) == DeserializationError::Ok) {
        String commandId = cmdDoc["id"].as<String>();
        String commandType = cmdDoc["type"].as<String>();
        String payload = cmdDoc["payload"].as<String>();
        
        Serial.print("🔍 COMMAND: Parsed - ID: '");
        Serial.print(commandId);
        Serial.print("', Type: '");
        Serial.print(commandType);
        Serial.print("', Payload: '");
        Serial.print(payload);
        Serial.println("'");
        
        if (commandId.length() == 0 || commandId == "null") {
          Serial.println("❌ COMMAND: Invalid command ID (null or empty), removing from queue");
          popCommand();
      return;
        }
        
        CommandType type = parseCommandType(commandType);
        
        if (executeCommand(commandId, type, payload)) {
          if (popCommand()) {
            Serial.println("🗑️ COMMAND: Command removed from queue");
          }
  } else {
          Serial.println("❌ COMMAND: Failed to execute command, removing from queue");
          popCommand(); // Remove failed command to prevent infinite loop
        }
      } else {
        Serial.println("❌ COMMAND: Failed to parse command JSON, removing from queue");
        popCommand(); // Remove invalid command
      }
    }
  }
}


static void printQueuedEvents() {
  Serial.println();
  Serial.println("================ QUEUE STATUS =================");
  
  size_t qSize = queueSize();
  Serial.print("📋 Queue size: ");
  Serial.print(qSize);
  Serial.println(" bytes");
  
  if (qSize == 0) {
    Serial.println("✅ No events in queue");
    return;
  }
  
  Serial.println("📝 Queued events:");
  Serial.println("------------------------------------------------");
  
  if (!ensureQueue()) {
    Serial.println("❌ Failed to access queue file");
    return;
  }
  
  File f = LittleFS.open(EVENT_QUEUE_FILE, "r");
  if (!f) {
    Serial.println("❌ Failed to open queue file");
    return;
  }
  
  int eventCount = 0;
  while (f.available()) {
    String line = f.readStringUntil('\n');
    if (line.length() > 0) {
      eventCount++;
      
      // Parse the JSON event
      StaticJsonDocument<256> eventDoc;
      if (deserializeJson(eventDoc, line) == DeserializationError::Ok) {
        String eventId = eventDoc["event_id"].as<String>();
        String treatment = eventDoc["treatment"].as<String>();
        uint32_t counter = eventDoc["counter"].as<uint32_t>();
        String timestamp = eventDoc["ts"].as<String>();
        
        Serial.print("#");
        Serial.print(eventCount);
        Serial.print(": ");
        Serial.print(treatment);
        Serial.print(" #");
        Serial.print(counter);
        Serial.print(" | ID: ");
        Serial.print(eventId);
        Serial.print(" | Time: ");
        Serial.println(timestamp);
  } else {
        Serial.print("#");
        Serial.print(eventCount);
        Serial.print(": [Raw JSON] ");
        Serial.println(line);
      }
    }
  }
  f.close();
  
  Serial.println("------------------------------------------------");
  Serial.print("Total events queued: ");
  Serial.println(eventCount);
  Serial.println("================================================");
}

// ============================== Actions ======================================
static void stopTreatment() {
  if (active==Treatment::None) return;
  
  // Turn OFF all treatment relays
  digitalWrite(RELAY_BASIC_PIN, RELAY_OFF_LEVEL);
  digitalWrite(RELAY_STANDARD_PIN, RELAY_OFF_LEVEL);
  digitalWrite(RELAY_PREMIUM_PIN, RELAY_OFF_LEVEL);
  
  // Turn OFF all LED mirror relays
  digitalWrite(LED_BASIC_PIN, RELAY_OFF_LEVEL);
  digitalWrite(LED_STANDARD_PIN, RELAY_OFF_LEVEL);
  digitalWrite(LED_PREMIUM_PIN, RELAY_OFF_LEVEL);
  
  active=Treatment::None;
  activeDurationMs=0;
  activeStartMs=0;
  drawMain();
}

static void enqueueTreatmentEvent(Treatment t, uint32_t counterVal) {
  StaticJsonDocument<512> body;
  body["device_id"] = deviceId.length()?deviceId:"esp32-sim";
  body["firmware"] = FIRMWARE_VERSION;
  body["event_id"] = generateEventId(t, counterVal);
  body["event"] = "treatment";
  body["treatment"] = treatmentName(t);
  body["counter"] = counterVal;
  body["ts"] = makeIsoNow();
  
  // Add current counter state for backend synchronization
  JsonObject counters = body.createNestedObject("current_counters");
  counters["basic"] = counterB;
  counters["standard"] = counterS;
  counters["premium"] = counterP;
  
  String line; serializeJson(body, line);
  
  if (appendEventToQueue(line)) {
    Serial.print("📝 QUEUE: Event queued successfully - ");
    Serial.print(treatmentName(t));
    Serial.print(" #");
    Serial.print(counterVal);
    Serial.print(" (ID: ");
    Serial.print(generateEventId(t, counterVal));
    Serial.print(")");
    Serial.print(" | Queue size: ");
    Serial.println(queueSize());
  } else {
    Serial.println("❌ QUEUE: Failed to queue event - storage full or error");
  }
}

static void startTimer(Treatment t) {
  if (active!=Treatment::None) return;
  switch (t) { 
    case Treatment::Basic: 
      activeDurationMs=DURATION_B_MS; 
      counterB++; 
      enqueueTreatmentEvent(t,counterB); 
      // Activate Basic treatment relay + LED mirror
      digitalWrite(RELAY_BASIC_PIN, RELAY_ON_LEVEL);
      digitalWrite(LED_BASIC_PIN, RELAY_ON_LEVEL);
      break; 
    case Treatment::Standard: 
      activeDurationMs=DURATION_S_MS; 
      counterS++; 
      enqueueTreatmentEvent(t,counterS); 
      // Activate Standard treatment relay + LED mirror
      digitalWrite(RELAY_STANDARD_PIN, RELAY_ON_LEVEL);
      digitalWrite(LED_STANDARD_PIN, RELAY_ON_LEVEL);
      break; 
    case Treatment::Premium: 
      activeDurationMs=DURATION_P_MS; 
      counterP++; 
      enqueueTreatmentEvent(t,counterP); 
      // Activate Premium treatment relay + LED mirror
      digitalWrite(RELAY_PREMIUM_PIN, RELAY_ON_LEVEL);
      digitalWrite(LED_PREMIUM_PIN, RELAY_ON_LEVEL);
      break; 
    default: return; 
  }
  saveCounters(); active=t; activeStartMs=millis(); drawTimer();
}

// ================================= Setup/Loop ================================
void setup(){
  Serial.begin(115200); while(!Serial){}
  Serial.println(); Serial.println("Ozone Machine (SIM) starting...");
  EEPROM.begin(EEPROM_SIZE); loadCounters(); loadWifiCreds(); loadIdentity();
  
  // Increment reset counter to ensure unique event IDs after reset
  resetCounter++;
  saveCounters();
  Serial.print("🔄 RESET: Reset counter incremented to ");
  Serial.println(resetCounter); 
  if (ensureQueue()) {
    Serial.println("✅ STORAGE: LittleFS queue initialized");
    size_t qSize = queueSize();
    if (qSize > 0) {
      Serial.print("📋 QUEUE: Found ");
      Serial.print(qSize);
      Serial.println(" bytes of pending events from previous session");
    } else {
      Serial.println("📋 QUEUE: No pending events");
    }
  } else {
    Serial.println("❌ STORAGE: Failed to initialize LittleFS queue");
  }
  
  if (ensureCommandQueue()) {
    Serial.println("✅ COMMAND: Command queue initialized");
    size_t cmdSize = commandQueueSize();
    if (cmdSize > 0) {
      Serial.print("📋 COMMAND: Found ");
      Serial.print(cmdSize);
      Serial.println(" bytes of pending commands from previous session");
    } else {
      Serial.println("📋 COMMAND: No pending commands");
    }
  } else {
    Serial.println("❌ COMMAND: Failed to initialize command queue");
  }

  // GPIO setup
  pinMode(BUTTON_BASIC_PIN, INPUT_PULLUP);      // BASIC
  pinMode(BUTTON_STANDARD_PIN, INPUT_PULLUP);    // STANDARD
  pinMode(BUTTON_PREMIUM_PIN, INPUT_PULLUP);  // PREMIUM
  
  // Treatment Relay pins
  pinMode(RELAY_BASIC_PIN, OUTPUT);
  pinMode(RELAY_STANDARD_PIN, OUTPUT);
  pinMode(RELAY_PREMIUM_PIN, OUTPUT);
  
  // LED Mirror Relay pins
  pinMode(LED_BASIC_PIN, OUTPUT);
  pinMode(LED_STANDARD_PIN, OUTPUT);
  pinMode(LED_PREMIUM_PIN, OUTPUT);
  
  // Initialize all relays to OFF state
  digitalWrite(RELAY_BASIC_PIN, RELAY_OFF_LEVEL);
  digitalWrite(RELAY_STANDARD_PIN, RELAY_OFF_LEVEL);
  digitalWrite(RELAY_PREMIUM_PIN, RELAY_OFF_LEVEL);
  digitalWrite(LED_BASIC_PIN, RELAY_OFF_LEVEL);
  digitalWrite(LED_STANDARD_PIN, RELAY_OFF_LEVEL);
  digitalWrite(LED_PREMIUM_PIN, RELAY_OFF_LEVEL);

  // RTC setup
  if (g_rtc.begin()) {
    if (g_rtc.lostPower()) {
      Serial.println("RTC lost power, setting to compile time");
      g_rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
    }
    DateTime now = g_rtc.now();
    Serial.print("RTC time: "); Serial.println(now.timestamp());
  } else {
    Serial.println("RTC init failed (continuing with millis fallback)");
  }

  WiFi.mode(WIFI_AP_STA); 
  WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASS);
  
  Serial.print("📡 WIFI: Starting AP '");
  Serial.print(WIFI_AP_SSID);
  Serial.print("' with IP: ");
  Serial.println(WiFi.softAPIP());
  
  Serial.print("📡 WIFI: Connecting STA to '");
  Serial.print(wifiSsid);
  Serial.print("' with password '");
  Serial.print(wifiPass);
  Serial.println("'");
  
  WiFi.begin(wifiSsid.c_str(), wifiPass.c_str());
  
  uint32_t start = millis(); 
  while (WiFi.status()!=WL_CONNECTED && millis()-start<15000) { 
    delay(250); 
    Serial.print('.'); 
    if (WiFi.status() == WL_CONNECT_FAILED) {
      Serial.println("\n❌ WIFI: Connection failed - check credentials");
      break;
    }
  }
  Serial.println(); 
  
  if (WiFi.status()==WL_CONNECTED) { 
    Serial.print("✅ WIFI: STA connected! IP: "); 
    Serial.println(WiFi.localIP());
    Serial.print("📡 WIFI: Gateway: ");
    Serial.println(WiFi.gatewayIP());
    Serial.print("📡 WIFI: DNS: ");
    Serial.println(WiFi.dnsIP());
    Serial.print("📡 WIFI: RSSI: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");

    // Sync RTC from NTP in KL timezone
    if (syncRTCFromNTP()) {
      Serial.println("⏱️ NTP: RTC synchronized to Kuala Lumpur time");
    }
  } else { 
    Serial.println("❌ WIFI: STA failed, AP-only active");
    wifiStats.disconnections++; // Track disconnection events
    Serial.print("📡 WIFI: Final status: ");
    wl_status_t status = WiFi.status();
    switch(status) {
      case WL_NO_SSID_AVAIL: Serial.println("No SSID available"); break;
      case WL_CONNECT_FAILED: Serial.println("Connection failed"); break;
      case WL_CONNECTION_LOST: Serial.println("Connection lost"); break;
      case WL_DISCONNECTED: Serial.println("Disconnected"); break;
      case WL_IDLE_STATUS: Serial.println("Idle"); break;
      default: Serial.print("Unknown ("); Serial.print(status); Serial.println(")"); break;
    }
  }

  // Force handshake if identity is missing or looks like pending-*
  if (deviceId.length()==0 || deviceToken.length()==0 || deviceId.indexOf("pending-")==0) {
    Serial.println("🔐 HANDSHAKE: Performing device handshake (identity missing or pending)");
    if (!performHandshake()) {
      Serial.println("❌ HANDSHAKE: Failed - will retry later");
    }
  }
  
  drawMain();
}

void loop(){
  // Buttons → actions
  bool b = digitalRead(BUTTON_BASIC_PIN) == LOW;
  bool s = digitalRead(BUTTON_STANDARD_PIN) == LOW;
  bool p = digitalRead(BUTTON_PREMIUM_PIN) == LOW;
  
  if (b && !btnBLast) { startTimer(Treatment::Basic); }
  if (s && !btnSLast) { startTimer(Treatment::Standard); }
  if (p && !btnPLast) { btnPHoldStart = millis(); }
  if (!p && btnPLast) {
    // short release: if active already, ignore here; starting PREMIUM handled on press
    if (active == Treatment::None) {
      // start premium on tap
      startTimer(Treatment::Premium);
    }
    btnPHoldStart = 0;
  }
  if (p && active != Treatment::None && btnPHoldStart && (millis() - btnPHoldStart >= 2000)) {
    stopTreatment();
    btnPHoldStart = 0;
  }
  btnBLast = b; btnSLast = s; btnPLast = p;

  if (active!=Treatment::None) { uint32_t elapsed=(uint32_t)(millis()-activeStartMs); if (elapsed>=activeDurationMs) stopTreatment(); else if (elapsed%1000<50) drawTimer(); }

  if (WiFi.status()==WL_CONNECTED) {
    // Monitor connection quality periodically
    uint32_t now = millis();
    if (now - lastConnectionCheck >= 10000) { // Every 10 seconds
      monitorConnectionQuality();
      lastConnectionCheck = now;
    }
    
    // Perform ping tests for packet loss detection
    if (now - lastPingTest >= 30000) { // Every 30 seconds
      uint32_t latency = performPingTest();
      if (latency > 0) {
        Serial.print("🏓 PING: ");
        Serial.print(latency);
        Serial.println("ms");
      } else {
        Serial.println("🏓 PING: Failed");
      }
      lastPingTest = now;
    }
    
    // Update connection quality score
    if (now - lastStatsUpdate >= 60000) { // Every 60 seconds
      updateConnectionQualityScore();
      lastStatsUpdate = now;
    }
    
    if (deviceId.length()==0 || deviceToken.length()==0) { 
      Serial.println("🔐 HANDSHAKE: Performing device handshake...");
      if (performHandshake()) {
        Serial.println("✅ HANDSHAKE: Success - device registered");
      } else {
        Serial.println("❌ HANDSHAKE: Failed - will retry");
      }
    }
    
    // Process command queue first (higher priority)
    processCommandQueue();
    
    // Poll for new commands
    uint32_t now = millis();
    if (now - lastCommandPoll >= COMMAND_POLL_INTERVAL_MS) {
      Serial.println("📡 COMMAND: Automatic command poll...");
      if (pollCommands()) {
        Serial.println("✅ COMMAND: Poll successful");
        commandRetryDelay = RETRY_BASE_DELAY_MS;
        commandRetryAttempts = 0;
      } else {
        commandRetryDelay = nextBackoffMs();
        commandRetryAttempts++;
        Serial.print("⏰ COMMAND: Poll failed, next retry in ");
        Serial.print(commandRetryDelay / 1000);
        Serial.println("s");
      }
      lastCommandPoll = now;
    }
    
    // Process event queue
    size_t qSize = queueSize();
    if (qSize > 0) {
      if (now - lastUploadAttempt >= currentRetryDelay) {
        Serial.print("📤 QUEUE: Processing queue (");
        Serial.print(qSize);
        Serial.print(" bytes) - Attempt #");
        Serial.print(retryAttempts + 1);
        Serial.print(" | Next retry in: ");
        Serial.print(currentRetryDelay / 1000);
        Serial.println("s");
        
        String line = readNextEvent();
        if (line.length() > 0) {
          // Parse event to show what we're uploading
          StaticJsonDocument<256> eventDoc;
          if (deserializeJson(eventDoc, line) == DeserializationError::Ok) {
            String eventId = eventDoc["event_id"].as<String>();
            String treatment = eventDoc["treatment"].as<String>();
            uint32_t counter = eventDoc["counter"].as<uint32_t>();
            Serial.print("📤 QUEUE: Uploading ");
            Serial.print(treatment);
            Serial.print(" #");
            Serial.print(counter);
            Serial.print(" (ID: ");
            Serial.print(eventId);
            Serial.println(")");
          }
          
          if (uploadEventJson(line)) {
            if (popEvent()) {
              Serial.println("🗑️ QUEUE: Event removed from queue");
              resetBackoff();
              Serial.println("✅ QUEUE: Upload successful, retry delay reset");
            } else {
              Serial.println("❌ QUEUE: Failed to remove event from queue");
            }
          } else {
            currentRetryDelay = nextBackoffMs();
            Serial.print("⏰ QUEUE: Upload failed, next retry in ");
            Serial.print(currentRetryDelay / 1000);
            Serial.println("s");
          }
        } else {
          Serial.println("❌ QUEUE: Failed to read event from queue");
        }
        lastUploadAttempt = now;
      }
    } else { 
      resetBackoff(); 
    }
  } else {
    // WiFi not connected - attempt periodic reconnection
    uint32_t now = millis();
    if (now - lastReconnectAttempt >= reconnectDelay) {
      Serial.print("🔄 WIFI: Periodic reconnection attempt (");
      Serial.print(reconnectAttempts + 1);
      Serial.println(")");
      
      if (attemptWiFiReconnection()) {
        Serial.println("✅ WIFI: Periodic reconnection successful");
      } else {
        Serial.print("❌ WIFI: Periodic reconnection failed, next attempt in ");
        Serial.print(reconnectDelay / 1000);
        Serial.println(" seconds");
      }
      
      lastReconnectAttempt = now;
    }
    
    // Show queue status periodically when offline
    static uint32_t lastQueueStatus = 0;
    if (now - lastQueueStatus >= 10000) { // Every 10 seconds
      size_t qSize = queueSize();
      size_t cmdSize = commandQueueSize();
      if (qSize > 0 || cmdSize > 0) {
        Serial.print("📱 OFFLINE: Event queue: ");
        Serial.print(qSize);
        Serial.print(" bytes, Command queue: ");
        Serial.print(cmdSize);
        Serial.print(" bytes pending | Next reconnect in: ");
        Serial.print((reconnectDelay - (now - lastReconnectAttempt)) / 1000);
        Serial.println("s");
      }
      lastQueueStatus = now;
    }
  }

  delay(50); // Reduced loop frequency from 50Hz to 20Hz for even lower power consumption
}


