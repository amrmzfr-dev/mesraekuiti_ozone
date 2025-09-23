#ifndef PINS_H
#define PINS_H

// Pin definitions for ESP32 LCD + Buttons + Relay System
// Based on the wiring diagram provided

// 1) LCD I2C Pins (20x4 via PCF8574/HD44780)
#define LCD_SDA_PIN 21    // D21
#define LCD_SCL_PIN 22    // D22
#define LCD_ADDRESS 0x27  // Common I2C address for LCD backpacks

// 3) Button Pins (with internal pull-up resistors) — B / S / P
// Use INPUT_PULLUP and wire buttons to GND
#define BUTTON_UP_PIN 27          // BASIC  (D27)
#define BUTTON_DOWN_PIN 14        // STANDARD (D14)
#define BUTTON_SELECT_PIN 15      // PREMIUM (D15)

// 2) Relay Control (single channel shared by B/S/P)
#define RELAY_PIN 23              // D23 single relay channel
// Backward-compatibility aliases (all map to the same physical relay)
#define RELAY_B_PIN RELAY_PIN
#define RELAY_P_PIN RELAY_PIN
#define RELAY_S_PIN RELAY_PIN

// 4) RTC (DS3231) I2C on second bus (Wire1)
#define RTC_SDA_PIN 25            // D25
#define RTC_SCL_PIN 26            // D26
#define RTC_ADDRESS 0x68

// System Constants
#define DEBOUNCE_DELAY 50      // Button debounce time in ms
#define RELAY_ON_TIME 500      // Relay activation time in ms
#define LCD_COLS 16            // LCD columns
#define LCD_ROWS 2             // LCD rows

// Menu States
enum MenuState {
  MENU_B = 0,
  MENU_P = 1,
  MENU_S = 2
};

// Unified pin map list for easy iteration/diagnostics
// Keeps legacy #defines above for backwards compatibility
#ifdef __cplusplus
struct PinEntry {
  const char* label;
  int pin;
};

static const PinEntry PIN_MAP[] = {
  // LCD I2C
  {"LCD_SDA", LCD_SDA_PIN},
  {"LCD_SCL", LCD_SCL_PIN},

  // Buttons
  {"BUTTON_UP", BUTTON_UP_PIN},
  {"BUTTON_DOWN", BUTTON_DOWN_PIN},
  {"BUTTON_SELECT", BUTTON_SELECT_PIN},

  // Relay (single)
  {"RELAY", RELAY_PIN},

  // RTC I2C
  {"RTC_SDA", RTC_SDA_PIN},
  {"RTC_SCL", RTC_SCL_PIN}
};

static const size_t PIN_MAP_COUNT = sizeof(PIN_MAP) / sizeof(PIN_MAP[0]);
#endif

#endif // PINS_H
