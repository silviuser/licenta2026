<#
  HR Helper - porneste toate serviciile in Windows Terminal, fiecare in tab-ul lui.

  Ruleaza-l din PROPRIUL tau terminal (sau click-dreapta -> "Run with PowerShell"),
  din folderul app:

      cd C:\Users\silvi\Desktop\licenta2026\app
      .\start-all.ps1

  Se deschide o fereastra Windows Terminal cu 3 tab-uri:
      NLP :8000  |  Backend :8080  |  Frontend :5173

  Postgres trebuie sa ruleze deja (serviciul Windows postgresql-x64-...).
  Opreste NLP / backend / frontend cu:   .\start-all.ps1 -Stop
  (Postgres e lasat pornit.)
#>

param(
    [ValidateSet('all', 'nlp', 'backend', 'frontend')]
    [string]$Service = 'all',
    [switch]$Stop
)

$root = $PSScriptRoot

# --- Gaseste JDK 21 (Adoptium). Cade elegant daca versiunea exacta difera. ---
function Resolve-Jdk {
    $preferred = 'C:\Program Files\Eclipse Adoptium\jdk-21.0.11.10-hotspot'
    if (Test-Path $preferred) { return $preferred }
    $any = Get-ChildItem 'C:\Program Files\Eclipse Adoptium' -Directory -Filter 'jdk-21*' -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | Select-Object -First 1
    if ($any) { return $any.FullName }
    if ($env:JAVA_HOME) { return $env:JAVA_HOME }
    return $preferred  # ultima varianta; gradlew va da o eroare clara
}

# ================= Launchere per serviciu (ruleaza in fiecare tab) =================

function Start-Nlp {
    $env:HRHELPER_API_WARMUP_ON_STARTUP = 'false'   # boot rapid; encoderul se incarca la prima cerere
    $env:PYTHONPATH = "$root\nlp-service\src"
    Set-Location "$root\nlp-service"
    Write-Host 'NLP service -> http://localhost:8000  (docs: /docs)' -ForegroundColor Cyan
    .\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
}

function Start-Backend {
    $env:JAVA_HOME = Resolve-Jdk
    Set-Location "$root\backend"
    Write-Host "JAVA_HOME = $env:JAVA_HOME" -ForegroundColor DarkGray
    Write-Host 'Backend -> http://localhost:8080  (Swagger: /swagger-ui.html)' -ForegroundColor Cyan
    .\gradlew.bat bootRun
}

function Start-Frontend {
    Set-Location "$root\frontend"
    Write-Host 'Frontend -> http://localhost:5173' -ForegroundColor Cyan
    npm run dev
}

# Cand scriptul e chemat pentru UN singur serviciu (dintr-un tab), ruleaza-l si ramai.
switch ($Service) {
    'nlp'      { Start-Nlp;      return }
    'backend'  { Start-Backend;  return }
    'frontend' { Start-Frontend; return }
}

# ================= -Stop: opreste NLP / backend / frontend =================

if ($Stop) {
    Get-NetTCPConnection -LocalPort 8000, 8080, 5173 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -Expand OwningProcess -Unique |
        ForEach-Object { try { Stop-Process -Id $_ -Force -ErrorAction Stop } catch {} }
    Write-Host 'Oprit NLP / backend / frontend (Postgres lasat pornit).' -ForegroundColor Yellow
    return
}

# ============================ Service = 'all' ============================

# 0) Postgres pornit? (port 5432)
if (-not (Get-NetTCPConnection -LocalPort 5432 -State Listen -ErrorAction SilentlyContinue)) {
    Write-Host 'ATENTIE: nimic nu asculta pe 5432 - porneste Postgres inainte.' -ForegroundColor Red
    Write-Host '         (serviciul Windows postgresql-x64-...; baza "hrhelper")' -ForegroundColor Red
    Write-Host '         Fara baza de date, backend-ul crapa la pornire.' -ForegroundColor Red
    Write-Host ''
}

# 1) Windows Terminal instalat?
if (-not (Get-Command wt.exe -ErrorAction SilentlyContinue)) {
    Write-Host 'Windows Terminal (wt) nu e gasit. Instaleaza-l din Microsoft Store,' -ForegroundColor Red
    Write-Host 'sau foloseste .\run-all.ps1 (ferestre PowerShell separate).' -ForegroundColor Red
    return
}

$self = $PSCommandPath

# 2) Deschide Windows Terminal cu 3 tab-uri. Fiecare tab re-cheama acest script
#    pentru un singur serviciu. Backtick-semicolon ( `; ) e delimitatorul de tab
#    pentru wt (nu separator de instructiune PowerShell).
wt --title 'NLP :8000'          powershell -NoExit -ExecutionPolicy Bypass -File "$self" -Service nlp `
    `; new-tab --title 'Backend :8080'   powershell -NoExit -ExecutionPolicy Bypass -File "$self" -Service backend `
    `; new-tab --title 'Frontend :5173'  powershell -NoExit -ExecutionPolicy Bypass -File "$self" -Service frontend

Write-Host ''
Write-Host 'Am pornit Windows Terminal cu 3 tab-uri (NLP, Backend, Frontend).' -ForegroundColor Green
Write-Host 'Dupa ce termina de pornit:' -ForegroundColor Green
Write-Host '  Frontend : http://localhost:5173'
Write-Host '  Backend  : http://localhost:8080   (Swagger: /swagger-ui.html)'
Write-Host '  NLP      : http://localhost:8000   (docs: /docs)'
Write-Host ''
Write-Host 'Opreste tot cu:  .\start-all.ps1 -Stop' -ForegroundColor DarkGray
