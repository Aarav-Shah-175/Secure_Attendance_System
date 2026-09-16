Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Secure Attendance System -- Agent Daemon"   -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
..\venv\Scripts\Activate.ps1
Write-Host "Virtual environment activated." -ForegroundColor Yellow
cd ..
Write-Host ""
Write-Host "  Teacher and Students open:" -ForegroundColor White
Write-Host "  http://13-127-69-218.sslip.io:8000" -ForegroundColor Green
Write-Host ""
.\venv\Scripts\python.exe -m attendance_agent --verbose