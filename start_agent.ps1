Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Secure Attendance System -- Agent Daemon"   -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
.\venv\Scripts\Activate.ps1
Write-Host "Virtual environment activated." -ForegroundColor Yellow
.\venv\Scripts\python.exe -m attendance_agent --verbose