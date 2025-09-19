@echo off
echo ESP32 LCD Test Upload Script
echo ============================
echo.
echo Make sure your ESP32 is connected via USB
echo.
echo Trying common COM ports...
echo.

REM Try common COM ports
for %%p in (COM3 COM4 COM5 COM6 COM7 COM8 COM9 COM10) do (
    echo Trying %%p...
    pio run --target upload --upload-port %%p 2>nul
    if %errorlevel% == 0 (
        echo.
        echo SUCCESS! Uploaded to %%p
        echo.
        echo Now opening serial monitor...
        pio device monitor --port %%p --baud 115200
        goto :end
    )
)

echo.
echo Could not find ESP32 on any COM port
echo Please check:
echo 1. ESP32 is connected via USB
echo 2. Correct drivers are installed
echo 3. Try uploading manually with: pio run --target upload --upload-port COM[your_port]
echo.

:end
pause
