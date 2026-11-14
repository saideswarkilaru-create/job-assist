# Job Assist installer. Run by double-clicking "Install Job Assist.bat".
# Installs only what is missing, for the current user (no admin rights needed), then creates shortcuts.
# Safe to run again at any time (it repairs / updates).

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Host.UI.RawUI.WindowTitle = 'Job Assist setup'

function Say($msg, $color = 'Cyan') { Write-Host "`n>> $msg" -ForegroundColor $color }
function Fail($msg) {
    Write-Host "`n!! $msg" -ForegroundColor Red
    Write-Host "`nPress Enter to close." ; [void](Read-Host)
    exit 1
}
function Has-Winget { return [bool](Get-Command winget -ErrorAction SilentlyContinue) }
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine')
}

# ---------------------------------------------------------------- 1. Python 3.11 - 3.13
function Find-Python {
    foreach ($v in @('3.12', '3.11', '3.13')) {
        try {
            $exe = & py "-$v" -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe) { return $exe.Trim() }
        } catch { }
    }
    foreach ($cand in @('python', 'python3')) {
        try {
            $out = & $cand -c "import sys; print(sys.version_info[:2] >= (3,11) and sys.version_info[:2] <= (3,13), sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $out -like 'True *') { return $out.Substring(5).Trim() }
        } catch { }
    }
    return $null
}

Say 'Checking Python...'
$py = Find-Python
if (-not $py) {
    if (-not (Has-Winget)) {
        Start-Process 'https://www.python.org/downloads/release/python-3129/'
        Fail 'Python 3.12 is needed. The download page is open: install it (tick "Add python.exe to PATH"), then run this installer again.'
    }
    Say 'Installing Python 3.12 (one time, about 2 minutes)...' 'Yellow'
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Host
    Refresh-Path
    $py = Find-Python
    if (-not $py) { Fail 'Python was installed but could not be found. Please restart the computer and run this installer again.' }
}
Write-Host "   Python: $py"

# ---------------------------------------------------------------- 2. App environment + libraries
$venvPy = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    Say 'Creating the app environment...'
    & $py -m venv .venv
    if ($LASTEXITCODE -ne 0) { Fail 'Could not create the Python environment.' }
}
Say 'Installing app libraries (first time takes a few minutes)...'
& $venvPy -m pip install --upgrade pip --quiet --disable-pip-version-check
& $venvPy -m pip install -r requirements.txt --quiet --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Fail 'Installing libraries failed. Check your internet connection and run the installer again.' }
(Get-FileHash requirements.txt).Hash | Set-Content -Path '.venv\requirements.hash'

# ---------------------------------------------------------------- 3. Browser
Say 'Checking for a browser to drive...'
$chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
            "$env:LocalAppData\Google\Chrome\Application\chrome.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
$edge = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") |
        Where-Object { Test-Path $_ } | Select-Object -First 1
if ($chrome) { Write-Host '   Google Chrome found (used by default).' }
elseif ($edge) { Write-Host '   Microsoft Edge found (Chrome not installed, so the app will use Edge).' }
else {
    Say 'No Chrome or Edge found; downloading a built-in browser...' 'Yellow'
    & $venvPy -m playwright install chromium
}

# ---------------------------------------------------------------- 4. Screens (prebuilt in releases)
$ui = Join-Path $Root 'web\dist\web\browser\index.html'
if (-not (Test-Path $ui)) {
    Say 'Building the app screens (one time)...' 'Yellow'
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        if (-not (Has-Winget)) { Fail 'The app screens are missing. Ask for the release .zip (it includes them).' }
        winget install -e --id OpenJS.NodeJS.LTS --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Host
        Refresh-Path
    }
    Push-Location web
    npm ci --no-audit --no-fund ; npm run build
    Pop-Location
    if (-not (Test-Path $ui)) { Fail 'Building the screens failed.' }
}

# ---------------------------------------------------------------- 5. First-run data + shortcuts
& $venvPy -c "import sys; sys.path.insert(0, r'$Root'); from jobassist import db; db.init_db()"
if ($LASTEXITCODE -ne 0) { Fail 'Could not create the database.' }

Say 'Creating shortcuts...'
$shell = New-Object -ComObject WScript.Shell
$targets = @([Environment]::GetFolderPath('Desktop'), (Join-Path ([Environment]::GetFolderPath('Programs')) ''))
foreach ($dir in $targets) {
    $lnk = $shell.CreateShortcut((Join-Path $dir 'Job Assist.lnk'))
    $lnk.TargetPath = Join-Path $Root 'start.bat'
    $lnk.WorkingDirectory = $Root
    $lnk.WindowStyle = 7   # start minimized; the app opens in your browser
    $lnk.IconLocation = "$env:SystemRoot\System32\imageres.dll,109"
    $lnk.Description = 'Job Assist: find, screen and apply to jobs'
    $lnk.Save()
}

Say 'All set! Double-click "Job Assist" on your Desktop to start.' 'Green'
$go = Read-Host 'Start Job Assist now? (Y/n)'
if ($go -ne 'n' -and $go -ne 'N') { Start-Process -FilePath (Join-Path $Root 'start.bat') -WorkingDirectory $Root -WindowStyle Minimized }
