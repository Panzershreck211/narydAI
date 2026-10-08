@echo off
rem NaryadAI: one-click start for Windows. Parameters are passed to start.ps1 (-NoDemo, -NoOpen, -Stop).
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
echo.
pause
