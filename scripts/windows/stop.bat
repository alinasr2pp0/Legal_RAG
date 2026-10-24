@echo off
REM Double-click wrapper: runs scripts\windows\stop.ps1 (pass the same arguments through).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1" %*
