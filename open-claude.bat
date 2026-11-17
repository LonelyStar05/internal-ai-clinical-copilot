@echo off
setlocal
cd /d "%~dp0"
where claude >nul 2>nul
if errorlevel 1 (
  echo Khong tim thay Claude Code. Cai bang: npm install -g @anthropic-ai/claude-code
  pause
  exit /b 1
)
claude
if errorlevel 1 (
  echo.
  echo Claude Code da dung voi ma loi %errorlevel%.
  pause
)
endlocal
