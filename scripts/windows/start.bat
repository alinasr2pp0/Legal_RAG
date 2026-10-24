@echo off
REM Double-click wrapper: runs scripts\windows\start.ps1 (pass the same arguments through).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
