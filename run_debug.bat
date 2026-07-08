@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo UFC Keypad Debug Launcher
echo Repo: %CD%
echo ============================================================
echo.
echo [1/3] Running debug_probe.py ...
python debug_probe.py
echo.
echo [2/3] Running main.py ...
python main.py
echo.
echo [3/3] Checking logs ...
echo.
if exist ufc_bootstrap.log (
  echo --- ufc_bootstrap.log ---
  powershell -NoProfile -Command "Get-Content .\ufc_bootstrap.log -Tail 80"
) else (
  echo ufc_bootstrap.log not found in repo dir
)
echo.
if exist ufc_crash.log (
  echo --- ufc_crash.log ---
  powershell -NoProfile -Command "Get-Content .\ufc_crash.log -Tail 80"
) else (
  echo ufc_crash.log not found in repo dir
)
echo.
if exist startup_probe.log (
  echo --- startup_probe.log ---
  powershell -NoProfile -Command "Get-Content .\startup_probe.log -Tail 80"
) else (
  echo startup_probe.log not found in repo dir
)
echo.
echo Temp logs may also be at: %TEMP%\ufc_bootstrap.log, %TEMP%\ufc_crash.log, %TEMP%\startup_probe.log
echo.
pause
