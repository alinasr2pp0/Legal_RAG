@echo off
REM Double-click wrapper for scripts\windows\loadtest.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0loadtest.ps1" %*
