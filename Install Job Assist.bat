@echo off
rem Double-click to install (or repair) Job Assist. No admin rights needed.
rem If anything goes wrong, this window stays open and a log is saved as install-log.txt.
setlocal
set "HERE=%~dp0"
cd /d "%HERE%"
title Job Assist setup

rem 1) Still inside the .zip? (Windows runs it from a temporary copy and the other files are missing.)
echo "%HERE%" | findstr /i /c:".zip\\" >nul && goto :inzip

rem 2) The installer script must sit next to this file.
if not exist "%HERE%installer\install.ps1" goto :missing

rem 3) Windows PowerShell must be available.
where powershell >nul 2>nul || goto :nops

powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%installer\install.ps1" %*
if errorlevel 1 (
  echo.
  echo  Setup did not finish. Details are in: %HERE%install-log.txt
  echo  Send that file to whoever gave you Job Assist.
  echo.
  pause
  exit /b 1
)
exit /b 0

:inzip
echo.
echo  Job Assist is still inside the .zip file, so it can't be installed from here.
echo.
echo   1. Close this window.
echo   2. Right-click JobAssist.zip and choose "Extract All...", then click Extract.
echo   3. Open the extracted JobAssist folder and double-click "Install Job Assist.bat" there.
echo.
pause
exit /b 1

:missing
echo.
echo  The "installer" folder is missing next to this file:
echo    %HERE%
echo.
echo  Extract the WHOLE zip (right-click JobAssist.zip, "Extract All...") and run
echo  "Install Job Assist.bat" from the extracted JobAssist folder.
echo.
pause
exit /b 1

:nops
echo.
echo  Windows PowerShell is missing or blocked on this PC (often by antivirus or a work policy).
echo  Job Assist needs it to install. Ask the PC's owner or IT to allow powershell.exe, then try again.
echo.
pause
exit /b 1
