$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
if (-not (Test-Path -LiteralPath "$ProjectRoot\.venv\Scripts\python.exe")) { throw 'Run .\setup_local.ps1 first.' }

$Backend = Start-Process -FilePath "$ProjectRoot\.venv\Scripts\python.exe" -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','10000','--reload' -WorkingDirectory "$ProjectRoot\backend" -PassThru -WindowStyle Hidden
$Frontend = Start-Process -FilePath 'npm.cmd' -ArgumentList 'run','dev' -WorkingDirectory "$ProjectRoot\frontend" -PassThru -WindowStyle Hidden
Write-Host 'EMOTO development servers started.' -ForegroundColor Green
Write-Host 'Frontend: http://localhost:5173'
Write-Host 'API docs: http://localhost:10000/api/docs'
Write-Host 'Press Ctrl+C to stop both servers.'
try {
    while (-not $Backend.HasExited -and -not $Frontend.HasExited) { Start-Sleep -Seconds 1 }
} finally {
    if (-not $Backend.HasExited) { Stop-Process -Id $Backend.Id }
    if (-not $Frontend.HasExited) { Stop-Process -Id $Frontend.Id }
}

