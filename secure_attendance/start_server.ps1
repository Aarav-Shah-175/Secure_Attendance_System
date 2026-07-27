# ============================================================
# Secure Attendance System -- Start Server Script
# Run this from the secure_attendance\ folder
# ============================================================

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Secure Attendance System -- HTTPS Dev Server"   -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
..\venv\Scripts\Activate.ps1

Write-Host ""
Write-Host "  Teacher and Students open:" -ForegroundColor White
Write-Host "  https://192-168-137-1.sslip.io:8000" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop the server." -ForegroundColor Gray
Write-Host ""

$certFile = "192-168-137-1.sslip.io+3.pem"
$keyFile  = "192-168-137-1.sslip.io+3-key.pem"

python manage.py runserver_plus 0.0.0.0:8000 --cert-file $certFile --key-file $keyFile
