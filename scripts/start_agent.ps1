param(
    [string]$IP
)

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Secure Attendance System -- Agent Daemon"   -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

# Check for SERVER_IP from parameter or .env
$envFile = Join-Path $PSScriptRoot "..\.env"
if ($IP) {
    $env:SERVER_IP = $IP
} elseif (Test-Path $envFile) {
    $line = Get-Content $envFile | Where-Object { $_ -match "^SERVER_IP\s*=\s*(.+)$" } | Select-Object -First 1
    if ($line -match "^SERVER_IP\s*=\s*(.+)$") {
        $IP = $Matches[1].Trim().Trim('"').Trim("'")
    }
}

if (-not $IP) {
    $IP = "127.0.0.1"
}

$domain = if ($IP -match "^\d+\.\d+\.\d+\.\d+$") { "$($IP.Replace('.', '-')).sslip.io" } else { $IP }
$portalUrl = "https://${domain}:8000"

Write-Host "Activating virtual environment..." -ForegroundColor Yellow
$venvActivate = Join-Path $PSScriptRoot "..\venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    & $venvActivate
}

Set-Location (Join-Path $PSScriptRoot "..")
Write-Host "Virtual environment active." -ForegroundColor Yellow
Write-Host ""
Write-Host "  Target Django Cloud Server:" -ForegroundColor Gray
Write-Host "  $portalUrl" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Teacher & Students open this URL in browser:" -ForegroundColor White
Write-Host "  $portalUrl" -ForegroundColor Green
Write-Host ""

$pythonExe = Join-Path $PSScriptRoot "..\venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

& $pythonExe -m attendance_agent --verbose