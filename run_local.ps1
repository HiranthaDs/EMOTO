$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
if (-not (Test-Path -LiteralPath "$ProjectRoot\.venv\Scripts\python.exe")) { throw 'Run .\setup_local.ps1 first.' }

Push-Location "$ProjectRoot\backend"
try { & "$ProjectRoot\.venv\Scripts\python.exe" -m alembic upgrade head } finally { Pop-Location }
Push-Location "$ProjectRoot\frontend"
try { & npm.cmd run build } finally { Pop-Location }

Write-Host 'EMOTO is starting with the Python backend (Docker is not required).' -ForegroundColor Green
Write-Host 'Application: http://localhost:10000'
Write-Host 'API docs:    http://localhost:10000/api/docs'
Write-Host 'Press Ctrl+C to stop the application.'
Set-Location "$ProjectRoot\backend"
& "$ProjectRoot\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 10000

