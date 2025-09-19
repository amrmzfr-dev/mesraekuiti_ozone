#ifndef PINS_H
#define PINS_H

// Pin definitions for ESP32 LCD + Buttons + Relay System
// Based on the wiring diagram provided

// LCD I2C Pins
#define LCD_SDA_PIN 21
#define LCD_SCL_PIN 22
#define LCD_ADDRESS 0x27  // Common I2C address for LCD backpacks

// Button Pins (with internal pull-up resistors)
#define BUTTON_UP_PIN 4
#define BUTTON_DOWN_PIN 0
#define BUTTON_SELECT_PIN 2

// Relay Control Pins
#define RELAY_B_PIN 23
#define RELAY_P_PIN 19
#define RELAY_S_PIN 18

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

#endif // PINS_H
