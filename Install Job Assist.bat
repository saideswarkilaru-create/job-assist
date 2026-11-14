@echo off
rem Double-click to install (or repair) Job Assist. No admin rights needed.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\install.ps1"
