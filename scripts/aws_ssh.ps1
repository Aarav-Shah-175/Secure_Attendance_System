param(
    [string]$IP,
    [string]$KeyPath = "C:\Users\shaha\OneDrive\Desktop\AWS\attendance-ec2-key.pem"
)

# If IP is not passed as an argument, look for SERVER_IP in .env
if (-not $IP) {
    $envFile = Join-Path $PSScriptRoot "..\.env"
    if (Test-Path $envFile) {
        $line = Get-Content $envFile | Where-Object { $_ -match "^SERVER_IP\s*=\s*(.+)$" } | Select-Object -First 1
        if ($line -match "^SERVER_IP\s*=\s*(.+)$") {
            $IP = $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
}

if (-not $IP) {
    $IP = Read-Host "Enter current EC2 Public IP"
}

if (-not (Test-Path $KeyPath)) {
    # Fallback to default .ssh folder if OneDrive path differs
    $altKey = Join-Path $env:USERPROFILE ".ssh\attendance-key.pem"
    if (Test-Path $altKey) {
        $KeyPath = $altKey
    }
}

Write-Host "Connecting to EC2 ($IP)..." -ForegroundColor Cyan
ssh -o StrictHostKeyChecking=accept-new -i "$KeyPath" "ubuntu@$IP"