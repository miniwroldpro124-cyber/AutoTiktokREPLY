# TikTok Auto Reply - khoi dong local (worker + panel localhost)
# Goi tu start_local.bat. Chay lai thu 2 van an toan: port da chong thi bo qua.
param(
    [switch]$Open   # mo panel tren trinh duyet
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Test-Port([int]$port) {
    $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    return [bool]$c
}

if (-not (Test-Port 8787)) {
    $py = Join-Path $root ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { Write-Host "thieu $py"; exit 1 }
    Start-Process -FilePath $py -ArgumentList "worker.py" `
        -WorkingDirectory $root -WindowStyle Minimized
    Write-Host "worker: khoi dong"
}
else { Write-Host "worker: da chay" }

if (-not (Test-Port 3000)) {
    $site = Join-Path $root "site"
    Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c", "npm run start > `"$root\panel.log`" 2>&1" `
        -WorkingDirectory $site -WindowStyle Minimized
    Write-Host "panel: khoi dong"
}
else { Write-Host "panel: da chay" }

if ($Open) {
    Start-Sleep -Seconds 4
    Start-Process "http://localhost:3000"
}

exit 0
