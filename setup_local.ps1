$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Python 3.12 or newer is required.' }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js 20 or newer is required.' }

$PythonVersion = python -c "import sys; print('.'.join(map(str, sys.version_info[:2])))"
$NodeVersion = node --version
Write-Host "Using Python $PythonVersion and Node $NodeVersion"

if (-not (Test-Path -LiteralPath '.venv')) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Push-Location frontend
try { npm ci } finally { Pop-Location }

New-Item -ItemType Directory -Force -Path backend\data, backend\data\uploads, backend\data\backups | Out-Null
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
    Write-Warning 'Created .env. Replace SESSION_SECRET and BOOTSTRAP_TOKEN before using the application.'
}
Push-Location backend
try { & ..\.venv\Scripts\python.exe -m alembic upgrade head } finally { Pop-Location }

Write-Host ''
Write-Host 'Setup complete.' -ForegroundColor Green
Write-Host '1. Edit .env and set random SESSION_SECRET and BOOTSTRAP_TOKEN values.'
Write-Host '2. Run .\run_local.ps1'
Write-Host '3. Open http://localhost:10000 and create the first administrator.'

