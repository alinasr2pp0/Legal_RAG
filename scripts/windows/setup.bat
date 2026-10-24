@echo off
REM Double-click wrapper: runs scripts\windows\setup.ps1 (pass the same arguments through).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
