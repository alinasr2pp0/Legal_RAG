@echo off
REM Double-click wrapper for scripts\windows\mlflow.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0mlflow.ps1" %*
