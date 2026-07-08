@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo UFC Keypad SAFE MODE Launcher
echo Repo: %CD%
echo ============================================================
echo.
echo Safe mode disables startup overlay, DCS-BIOS receiver thread, mouse hook, and native touch registration.
echo.
set UFC_SAFE_MODE=1
python main_safe.py
echo.
echo --- safe logs ---
if exist ufc_safe.log powershell -NoProfile -Command "Get-Content .\ufc_safe.log -Tail 100"
if exist ufc_bootstrap.log powershell -NoProfile -Command "Get-Content .\ufc_bootstrap.log -Tail 60"
if exist ufc_crash.log powershell -NoProfile -Command "Get-Content .\ufc_crash.log -Tail 100"
echo.
echo Temp logs may also be at: %TEMP%\ufc_safe.log, %TEMP%\ufc_bootstrap.log, %TEMP%\ufc_crash.log
echo.
pause
