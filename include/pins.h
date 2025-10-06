#ifndef PINS_H
#define PINS_H

// Pin definitions for ESP32 Buttons + Relay System
// Based on the wiring diagram provided

// 3) Button Pins (with internal pull-up resistors) — BASIC / STANDARD / PREMIUM
// Use INPUT_PULLUP and wire buttons to GND
#define BUTTON_BASIC_PIN 27       // BASIC  (D27)
#define BUTTON_STANDARD_PIN 14    // STANDARD (D14)
#define BUTTON_PREMIUM_PIN 12     // PREMIUM (D12) - moved from GPIO 15 (strapping pin)

// 2) Relay Control (6 channels: 3 treatment + 3 LED mirror)
// Treatment Relays
#define RELAY_BASIC_PIN 23        // D23 Basic treatment relay (IN1) - WORKING
#define RELAY_STANDARD_PIN 13     // D13 Standard treatment relay (IN2) - MOVED from GPIO 22 (BROKEN)
#define RELAY_PREMIUM_PIN 32      // D32 Premium treatment relay (IN3) - MOVED from GPIO 21 (BROKEN)

// LED Mirror Relays
#define LED_BASIC_PIN 19          // D19 Basic LED mirror relay (IN4)
#define LED_STANDARD_PIN 18       // D18 Standard LED mirror relay (IN5)
#define LED_PREMIUM_PIN 5         // D5 Premium LED mirror relay (IN6)

// Reserved for future expansion
// IN7 → Reset Counter Relay (GPIO 33)
// IN8 → Available for future use

// Reset Counter Pin (1-second activation)
#define RESET_COUNTER_PIN 33        // IN7 Reset counter relay (1-second pulse)

// Backward-compatibility aliases (map to new pins)
#define RELAY_PIN RELAY_BASIC_PIN
#define RELAY_B_PIN RELAY_BASIC_PIN
#define RELAY_S_PIN RELAY_STANDARD_PIN
#define RELAY_P_PIN RELAY_PREMIUM_PIN

// 4) RTC (DS3231) I2C on second bus (Wire1)
#define RTC_SDA_PIN 25            // D25
#define RTC_SCL_PIN 26            // D26
#define RTC_ADDRESS 0x68

// 5) SD Card Module - DISABLED (using EEPROM instead)
// SD card functionality removed, using EEPROM for storage

// System Constants
#define DEBOUNCE_DELAY 50      // Button debounce time in ms
#define RELAY_ON_TIME 500      // Relay activation time in ms
// Menu States
enum MenuState {
  MENU_BASIC = 0,
  MENU_PREMIUM = 1,
  MENU_STANDARD = 2
};

// Unified pin map list for easy iteration/diagnostics
// Keeps legacy #defines above for backwards compatibility
#ifdef __cplusplus
struct PinEntry {
  const char* label;
  int pin;
};

static const PinEntry PIN_MAP[] = {
  // Buttons
  {"BUTTON_BASIC", BUTTON_BASIC_PIN},     // GPIO 27
  {"BUTTON_STANDARD", BUTTON_STANDARD_PIN}, // GPIO 14
  {"BUTTON_PREMIUM", BUTTON_PREMIUM_PIN}, // GPIO 12

  // Treatment Relays
  {"RELAY_BASIC", RELAY_BASIC_PIN},      // IN1 (GPIO 23) - WORKING
  {"RELAY_STANDARD", RELAY_STANDARD_PIN}, // IN2 (GPIO 13) - MOVED from GPIO 22 (BROKEN)
  {"RELAY_PREMIUM", RELAY_PREMIUM_PIN},   // IN3 (GPIO 32) - MOVED from GPIO 21 (BROKEN)

  // LED Mirror Relays
  {"LED_BASIC", LED_BASIC_PIN},           // IN4 (GPIO 19)
  {"LED_STANDARD", LED_STANDARD_PIN},     // IN5 (GPIO 18)
  {"LED_PREMIUM", LED_PREMIUM_PIN},       // IN6 (GPIO 5)

  // Reset Counter Relay (IN7)
  {"RESET_COUNTER", RESET_COUNTER_PIN},   // IN7 GPIO 33 (1-second pulse)

  // RTC I2C
  {"RTC_SDA", RTC_SDA_PIN},               // GPIO 25
  {"RTC_SCL", RTC_SCL_PIN}                // GPIO 26
};

static const size_t PIN_MAP_COUNT = sizeof(PIN_MAP) / sizeof(PIN_MAP[0]);
#endif

#endif // PINS_H
