# One-line installer for Job Assist (Windows 10/11). Paste this into PowerShell:
#
#   irm https://raw.githubusercontent.com/saideswarkilaru-create/job-assist/main/get-jobassist.ps1 | iex
#
# It downloads the latest release zip, unblocks it, extracts it to Documents\JobAssist and runs the
# normal installer. Running it again updates Job Assist and keeps your data, resumes and sign-ins.
# Optional for testing: set $env:JOBASSIST_DIR (install folder) and $env:JOBASSIST_INSTALL_ARGS
# (e.g. "-NoShortcuts -NoPause -NoStart") before running.

$ErrorActionPreference = 'Stop'
try {
    if ($env:OS -ne 'Windows_NT') { throw 'Job Assist runs on Windows 10 or 11 only.' }
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

    $docs = [Environment]::GetFolderPath('MyDocuments')
    $dest = if ($env:JOBASSIST_DIR) { $env:JOBASSIST_DIR } else { Join-Path $docs 'JobAssist' }
    $parent = Split-Path -Parent $dest
    $url = 'https://github.com/saideswarkilaru-create/job-assist/releases/latest/download/JobAssist.zip'
    $zip = Join-Path $env:TEMP 'JobAssist-download.zip'
    $unpack = Join-Path $env:TEMP 'JobAssist-unpack'

    Write-Host "`n>> Downloading Job Assist..." -ForegroundColor Cyan
    $ProgressPreference = 'SilentlyContinue'   # makes the download much faster in Windows PowerShell
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    Unblock-File $zip

    Write-Host ">> Extracting to $dest ..." -ForegroundColor Cyan
    if (Test-Path $unpack) { Remove-Item $unpack -Recurse -Force }
    Expand-Archive -Path $zip -DestinationPath $unpack -Force
    New-Item -ItemType Directory -Force $dest | Out-Null
    # copy over an existing install: app files are replaced, data / resumes / logins are not in the zip so they stay
    Copy-Item -Path (Join-Path $unpack 'JobAssist\*') -Destination $dest -Recurse -Force
    Get-ChildItem $dest -Recurse -File | Unblock-File
    Remove-Item $unpack -Recurse -Force
    Remove-Item $zip -Force

    Write-Host ">> Starting the installer..." -ForegroundColor Cyan
    $installer = Join-Path $dest 'installer\install.ps1'
    $extra = if ($env:JOBASSIST_INSTALL_ARGS) { $env:JOBASSIST_INSTALL_ARGS -split '\s+' | Where-Object { $_ } } else { @() }
    & powershell -NoProfile -ExecutionPolicy Bypass -File $installer @extra
    if ($LASTEXITCODE -ne 0) { throw "The installer stopped. Details: $(Join-Path $dest 'install-log.txt')" }
}
catch {
    Write-Host "`n!! Job Assist could not be installed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host '   Take a screenshot of this window and send it to whoever shared Job Assist with you.'
}
