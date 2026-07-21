#requires -RunAsAdministrator
param(
    [string]$ProjectRoot = "C:\mental_health_website",
    [int]$Port = 80,
    [string]$TaskName = "MentalHealthWebsite",
    [switch]$ReseedDemoData,
    [switch]$SkipArticleCrawl
)

$ErrorActionPreference = "Stop"

function Assert-Command {
    param([string]$Name, [string]$InstallHint)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name was not found. $InstallHint"
    }
}

if (-not (Test-Path $ProjectRoot)) {
    throw "Project root not found: $ProjectRoot"
}

Set-Location $ProjectRoot

Assert-Command python "Install Python 3.11+ and add it to PATH."
Assert-Command npm.cmd "Install Node.js 20+ and add it to PATH."

if (-not (Test-Path "environment\requirements.txt")) {
    throw "Missing environment\requirements.txt. Copy the project's environment folder to $ProjectRoot first."
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

$envText = Get-Content ".env" -Raw
$envText = $envText -replace "(?m)^APP_ENV=.*$", "APP_ENV=development"
$envText = $envText -replace "(?m)^DATABASE_URL=.*$", "DATABASE_URL=sqlite:///./mental_health_v2.db"
$envText = $envText -replace "(?m)^REDIS_URL=.*$", "REDIS_URL="
$envText = $envText -replace "(?m)^CORS_ORIGINS=.*$", "CORS_ORIGINS=http://47.98.245.106,http://localhost:$Port"
Set-Content ".env" $envText -Encoding UTF8

if (-not (Test-Path ".venv")) {
    python -m venv ".venv"
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
& ".\.venv\Scripts\pip.exe" install -r "environment\requirements.txt"
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }

Push-Location "frontend"
npm.cmd ci
if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
Pop-Location

$dbPath = Join-Path $ProjectRoot "mental_health_v2.db"
if ($ReseedDemoData -or -not (Test-Path $dbPath)) {
    & ".\.venv\Scripts\python.exe" "seed.py"
    if ($LASTEXITCODE -ne 0) { throw "Database seed failed." }
} else {
    & ".\.venv\Scripts\python.exe" -c "from database.database import init_db; init_db()"
    if ($LASTEXITCODE -ne 0) { throw "Database initialization failed." }
    Write-Host "Existing database detected; skipped destructive demo seed. Use -ReseedDemoData to rebuild demo data."
}

if (-not $SkipArticleCrawl) {
    & ".\.venv\Scripts\python.exe" -m scripts.crawl_psychology_articles
    if ($LASTEXITCODE -ne 0) { throw "Article crawl failed." }
}

$pythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$uvicornArgs = "-m uvicorn backend.main:app --host 0.0.0.0 --port $Port"
$action = New-ScheduledTaskAction -Execute $pythonExe -Argument $uvicornArgs -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Days 0)

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null

New-NetFirewallRule -DisplayName "MentalHealthWebsite HTTP $Port" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -ErrorAction SilentlyContinue | Out-Null

Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 5

$health = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/api/health" -TimeoutSec 10
Write-Host "Deployment finished."
Write-Host "Local health: $($health.Content)"
Write-Host "Public URL: http://47.98.245.106"
