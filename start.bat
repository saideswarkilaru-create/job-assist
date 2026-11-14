@echo off
rem Double-click (or use the Desktop shortcut) to start Job Assist. It opens in your web browser.
cd /d "%~dp0"
title Job Assist (close this window to stop the app)
if not exist ".venv\Scripts\python.exe" (
  echo First start: setting things up...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\install.ps1"
  exit /b
)
".venv\Scripts\python.exe" run.py
if errorlevel 1 pause
