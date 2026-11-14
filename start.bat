@echo off
rem Double-click (or use the Desktop shortcut) to start Job Assist. It opens in your web browser.
cd /d "%~dp0"
title Job Assist (close this window to stop the app)
rem Use Windows' fixed folders: some PCs have a damaged PATH.
set "SYS=%SystemRoot%\System32"
set "PATH=%SYS%;%SystemRoot%;%SYS%\Wbem;%SYS%\WindowsPowerShell\v1.0;%PATH%"
if not exist ".venv\Scripts\python.exe" (
  echo First start: setting things up...
  call "%~dp0Install Job Assist.bat"
  exit /b
)
".venv\Scripts\python.exe" run.py
if errorlevel 1 pause
