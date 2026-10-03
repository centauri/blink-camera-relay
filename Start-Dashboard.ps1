$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$dashboardUrl = 'http://127.0.0.1:8787'
try {
    $existing = Invoke-RestMethod "$dashboardUrl/api/status" -TimeoutSec 2
    if ($null -ne $existing.cameras) { Start-Process $dashboardUrl; exit }
} catch {}
$pythonExe = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw 'The project Python environment is missing. See the Dashboard section in README.md.'
}
$entryPoint = Join-Path $projectRoot 'bridge\web.py'
Start-Process -FilePath $pythonExe -ArgumentList ('"' + $entryPoint + '"') -WorkingDirectory $projectRoot -WindowStyle Hidden
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $ready = Invoke-RestMethod "$dashboardUrl/api/status" -TimeoutSec 1
        Start-Process $dashboardUrl
        exit
    } catch { Start-Sleep -Milliseconds 200 }
}
throw 'Dashboard did not start. Run .venv\Scripts\python.exe bridge\web.py to see the startup error.'
