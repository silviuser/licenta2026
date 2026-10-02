# HR Helper — start all services in their own persistent windows.
# Run this from YOUR OWN terminal (or right-click → "Run with PowerShell").
# The windows stay open and keep running independently of any chat session.
#
#   cd C:\Users\silvi\Desktop\licenta2026\app
#   .\run-all.ps1
#
# Stop everything later with:  .\run-all.ps1 -Stop

param([switch]$Stop)

$root = $PSScriptRoot
$jdk  = "C:\Program Files\Eclipse Adoptium\jdk-21.0.11.10-hotspot"

if ($Stop) {
    Get-NetTCPConnection -LocalPort 8000, 8080, 5173 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -Expand OwningProcess -Unique |
        ForEach-Object { try { Stop-Process -Id $_ -Force -ErrorAction Stop } catch {} }
    Write-Host "Stopped NLP / backend / frontend (Postgres left running)." -ForegroundColor Yellow
    return
}

Write-Host "Starting HR Helper (Postgres must already be running as a Windows service)..." -ForegroundColor Cyan

# --- NLP service (:8000) — warmup off so it boots fast; encoder loads on first request ---
Start-Process powershell -ArgumentList '-NoExit', '-Command', @"
`$env:HRHELPER_API_WARMUP_ON_STARTUP='false'
`$env:PYTHONPATH='$root\nlp-service\src'
Set-Location '$root\nlp-service'
.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
"@

# --- Backend (:8080) ---
Start-Process powershell -ArgumentList '-NoExit', '-Command', @"
`$env:JAVA_HOME='$jdk'
Set-Location '$root\backend'
.\gradlew.bat bootRun
"@

# --- Frontend (:5173) ---
Start-Process powershell -ArgumentList '-NoExit', '-Command', @"
Set-Location '$root\frontend'
npm run dev
"@

Write-Host "Launched 3 windows. Once they finish booting:" -ForegroundColor Green
Write-Host "  Frontend : http://localhost:5173"
Write-Host "  Backend  : http://localhost:8080  (Swagger: /swagger-ui.html)"
Write-Host "  NLP      : http://localhost:8000  (docs: /docs)"
