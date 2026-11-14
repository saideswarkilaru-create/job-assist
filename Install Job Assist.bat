@echo off
rem Double-click to install (or repair) Job Assist. No admin rights needed.
rem If anything goes wrong, this window stays open and a log is saved as install-log.txt.
setlocal
set "HERE=%~dp0"
cd /d "%HERE%"
title Job Assist setup

rem Use Windows' fixed folders: some PCs have a damaged PATH ("'powershell' is not recognized").
set "SYS=%SystemRoot%\System32"
set "PATH=%SYS%;%SystemRoot%;%SYS%\Wbem;%SYS%\WindowsPowerShell\v1.0;%PATH%"
set "PS=%SYS%\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS%" for /f "delims=" %%p in ('"%SYS%\where.exe" pwsh 2^>nul') do set "PS=%%p"

rem 1) Still inside the .zip? (Windows runs it from a temporary copy and the other files are missing.)
echo "%HERE%" | "%SYS%\findstr.exe" /i /c:".zip\\" >nul && goto :inzip

rem 2) The installer script must sit next to this file.
if not exist "%HERE%installer\install.ps1" goto :missing

rem 3) PowerShell must be available.
if not exist "%PS%" goto :nops

"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%HERE%installer\install.ps1" %*
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
echo  Windows PowerShell was not found on this PC (expected at %SYS%\WindowsPowerShell).
echo  It may be blocked by antivirus or a work policy. Ask the PC's owner or IT to allow
echo  powershell.exe, then try again.
echo.
pause
exit /b 1
