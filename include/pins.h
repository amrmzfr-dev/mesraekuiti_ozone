#ifndef PINS_H
#define PINS_H

// Pin definitions for ESP32 Buttons + Relay System
// Based on the wiring diagram provided

// 3) Button Pins (with internal pull-up resistors) — BASIC / STANDARD / PREMIUM
// Use INPUT_PULLUP and wire buttons to GND
#define BUTTON_BASIC_PIN 27       // BASIC  (D27)
#define BUTTON_STANDARD_PIN 14    // STANDARD (D14)
#define BUTTON_PREMIUM_PIN 15     // PREMIUM (D15)

// 2) Relay Control (6 channels: 3 treatment + 3 LED mirror)
// Treatment Relays
#define RELAY_BASIC_PIN 23        // D23 Basic treatment relay (IN1)
#define RELAY_STANDARD_PIN 22     // D22 Standard treatment relay (IN2)
#define RELAY_PREMIUM_PIN 21      // D21 Premium treatment relay (IN3)

// LED Mirror Relays
#define LED_BASIC_PIN 19          // D19 Basic LED mirror relay (IN4)
#define LED_STANDARD_PIN 18       // D18 Standard LED mirror relay (IN5)
#define LED_PREMIUM_PIN 5         // D5 Premium LED mirror relay (IN6)

// Reserved for future expansion
// IN7 → Available for future use
// IN8 → Available for future use

// Backward-compatibility aliases (map to new pins)
#define RELAY_PIN RELAY_BASIC_PIN
#define RELAY_B_PIN RELAY_BASIC_PIN
#define RELAY_S_PIN RELAY_STANDARD_PIN
#define RELAY_P_PIN RELAY_PREMIUM_PIN

// 4) RTC (DS3231) I2C on second bus (Wire1)
#define RTC_SDA_PIN 25            // D25
#define RTC_SCL_PIN 26            // D26
#define RTC_ADDRESS 0x68

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
  {"BUTTON_BASIC", BUTTON_BASIC_PIN},
  {"BUTTON_STANDARD", BUTTON_STANDARD_PIN},
  {"BUTTON_PREMIUM", BUTTON_PREMIUM_PIN},

  // Treatment Relays
  {"RELAY_BASIC", RELAY_BASIC_PIN},      // IN1
  {"RELAY_STANDARD", RELAY_STANDARD_PIN}, // IN2
  {"RELAY_PREMIUM", RELAY_PREMIUM_PIN},   // IN3

  // LED Mirror Relays
  {"LED_BASIC", LED_BASIC_PIN},           // IN4
  {"LED_STANDARD", LED_STANDARD_PIN},     // IN5
  {"LED_PREMIUM", LED_PREMIUM_PIN},       // IN6

  // RTC I2C
  {"RTC_SDA", RTC_SDA_PIN},
  {"RTC_SCL", RTC_SCL_PIN}
};

static const size_t PIN_MAP_COUNT = sizeof(PIN_MAP) / sizeof(PIN_MAP[0]);
#endif

#endif // PINS_H
