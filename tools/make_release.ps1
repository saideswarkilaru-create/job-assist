# Build a clean, shareable JobAssist.zip (for the person who will use the app).
# Includes the prebuilt screens, so their PC needs no Node.js. Excludes your data, logins and resumes.
#   powershell -ExecutionPolicy Bypass -File tools\make_release.ps1

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host '>> Running tests...' -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed; not building a release.' }

Write-Host '>> Building screens...' -ForegroundColor Cyan
Push-Location web; npm run build; Pop-Location

$stage = Join-Path $env:TEMP 'JobAssist-release'
$out = Join-Path $Root 'release'
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force $stage, $out | Out-Null
$dest = Join-Path $stage 'JobAssist'

$include = @('jobassist', 'installer', 'adapters', 'config', 'tests', 'web\dist',
             'run.py', 'scheduled_run.py', 'start.bat', 'Install Job Assist.bat', 'requirements.txt', 'requirements-dev.txt', 'pytest.ini',
             'README.md', 'CLAUDE.md')
foreach ($item in $include) {
    $src = Join-Path $Root $item
    if (Test-Path $src) {
        $target = Join-Path $dest $item
        New-Item -ItemType Directory -Force (Split-Path $target -Parent) | Out-Null
        Copy-Item $src $target -Recurse -Force
    }
}
Get-ChildItem $dest -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
Remove-Item (Join-Path $dest 'config\profile.yaml') -ErrorAction SilentlyContinue

$zip = Join-Path $out 'JobAssist.zip'
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $dest -DestinationPath $zip
Write-Host ">> Release ready: $zip" -ForegroundColor Green
Write-Host '   Give this zip to the user. They unzip it and double-click "Install Job Assist.bat".'
