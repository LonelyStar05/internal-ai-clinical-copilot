@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1"
if errorlevel 1 (
  echo.
  echo Khoi dong that bai. Xem thong bao phia tren hoac thu muc logs.
  pause
)
endlocal
