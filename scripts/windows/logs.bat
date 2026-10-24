@echo off
REM Live log viewer: scripts\windows\logs.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0logs.ps1" %*
