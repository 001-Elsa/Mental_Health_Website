param(
  [string]$Python = "python",
  [string]$BaseUrl = "http://127.0.0.1:8000",
  [string]$ResultRoot = ""
)

$ErrorActionPreference = "Stop"
$workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $ResultRoot) {
  $ResultRoot = Join-Path $workspace ("benchmarks\results\cache-failure-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
}
elseif (-not [IO.Path]::IsPathRooted($ResultRoot)) {
  $ResultRoot = Join-Path $workspace $ResultRoot
}
New-Item -ItemType Directory -Path $ResultRoot -Force | Out-Null
$benchmark = Join-Path $workspace "tests\load\benchmark.py"
$override = Join-Path $workspace "tests\load\docker-compose.cache-benchmark.yml"
$compose = @("compose", "-p", "mental-health-cache-benchmark", "-f", (Join-Path $workspace "docker-compose.yml"), "-f", $override)
$endpoint = "/api/articles/?skip=0&limit=20"

function Invoke-DockerCompose {
  & docker @compose @args
  if ($LASTEXITCODE -ne 0) { throw "docker compose failed with exit code $LASTEXITCODE" }
}

function Wait-Api([int]$TimeoutSeconds = 120) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    try {
      $response = Invoke-RestMethod -Uri "$BaseUrl/api/health" -TimeoutSec 3
      if ($response.status -eq "ok") { return $response }
    }
    catch { Start-Sleep -Milliseconds 500 }
  } while ((Get-Date) -lt $deadline)
  throw "API did not become healthy within $TimeoutSeconds seconds"
}

function Invoke-Benchmark([string]$Label, [int]$Requests, [int]$Concurrency, [int]$Warmup, [string]$Output) {
  & $Python $benchmark --base-url $BaseUrl --endpoint $endpoint --requests $Requests `
    --concurrency $Concurrency --warmup $Warmup --label $Label --output $Output | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "benchmark '$Label' failed with exit code $LASTEXITCODE" }
}

# Keep credentials ephemeral and independent from the developer's .env file.
$env:BENCHMARK_SECRET_KEY = ([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
$env:BENCHMARK_METRICS_TOKEN = ([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
$env:METRICS_TOKEN = $env:BENCHMARK_METRICS_TOKEN
$startedAt = (Get-Date).ToUniversalTime().ToString("o")
$recovery = $null
$desktopInstall = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
  Where-Object { $_.DisplayName -like 'Docker Desktop*' } | Select-Object -First 1
$dataVhd = @(
  'D:\Docker_Desktop\docker-data\wsl\disk\docker_data.vhdx',
  (Join-Path $env:LOCALAPPDATA 'Docker\wsl\data\ext4.vhdx')
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

Push-Location $workspace
try {
  Invoke-DockerCompose up -d --build postgres redis api
  $initialHealth = Wait-Api
  Invoke-Benchmark "redis-healthy" 400 20 30 (Join-Path $ResultRoot "01-redis-healthy.json")

  Invoke-DockerCompose stop redis
  # Exactly one request records the closed-circuit socket failure and fallback.
  Invoke-Benchmark "redis-outage-first-failure" 1 1 0 (Join-Path $ResultRoot "02-outage-first-failure.json")
  # Run immediately, inside the five-second open-circuit window.
  # Keep this run below five seconds so every sample belongs to the same open
  # circuit window instead of silently mixing in a later Redis retry.
  Invoke-Benchmark "redis-outage-circuit-open" 100 20 0 (Join-Path $ResultRoot "03-circuit-open.json")
}
finally {
  Invoke-DockerCompose start redis
  Start-Sleep -Seconds 6
  $recovery = Wait-Api
  $metadata = [ordered]@{
    schema_version = "1.0"
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    started_at = $startedAt
    docker_server = (& docker version --format '{{.Server.Version}}')
    docker_desktop_version = $desktopInstall.DisplayVersion
    docker_desktop_install_location = $desktopInstall.InstallLocation
    docker_data_vhd = $dataVhd
    docker_data_vhd_bytes = if ($dataVhd) { (Get-Item -LiteralPath $dataVhd).Length } else { $null }
    compose_project = "mental-health-cache-benchmark"
    api_workers = 1
    endpoint = $endpoint
    stages = @(
      "01-redis-healthy.json",
      "02-outage-first-failure.json",
      "03-circuit-open.json"
    )
    recovery_health = $recovery
  }
  $metadata | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $ResultRoot "00-run-metadata.json") -Encoding UTF8
  Remove-Item Env:BENCHMARK_SECRET_KEY -ErrorAction SilentlyContinue
  Remove-Item Env:BENCHMARK_METRICS_TOKEN -ErrorAction SilentlyContinue
  Remove-Item Env:METRICS_TOKEN -ErrorAction SilentlyContinue
  Pop-Location
}

Write-Output "Raw benchmark reports: $ResultRoot"
