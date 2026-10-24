@echo off
REM Double-click wrapper for scripts\windows\install-monitoring.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-monitoring.ps1" %*
