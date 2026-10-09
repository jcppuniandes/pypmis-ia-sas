param(
  [string]$EnvFile = "deploy\vps\.env"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $EnvFile)) {
  throw "Missing $EnvFile. Copy deploy\vps\.env.example to $EnvFile and replace every change_this value."
}

$required = @(
  "POSTGRES_PASSWORD",
  "REDIS_PASSWORD",
  "AUTH_SECRET_KEY",
  "METRICS_TOKEN",
  "CORS_ORIGINS",
  "ALLOWED_HOSTS"
)

$values = @{}
Get-Content $EnvFile | ForEach-Object {
  $line = $_.Trim()
  if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
    return
  }
  $parts = $line.Split("=", 2)
  $values[$parts[0]] = $parts[1]
}

foreach ($key in $required) {
  if (-not $values.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($values[$key])) {
    throw "Missing required variable $key in $EnvFile."
  }
  if ($values[$key] -like "change_this*") {
    throw "Variable $key still has a placeholder value."
  }
}

if ($values["AUTH_SECRET_KEY"].Length -lt 64) {
  throw "AUTH_SECRET_KEY must have at least 64 characters."
}

foreach ($key in @("POSTGRES_PASSWORD", "REDIS_PASSWORD")) {
  if ($values[$key] -match '[:/@?#\[\]\s]') {
    throw "$key must be URL-safe because docker-compose.vps.yml builds connection URLs from it. Avoid spaces and : / @ ? # [ ]."
  }
}

if ($values["ALLOWED_HOSTS"].Contains("*")) {
  throw "ALLOWED_HOSTS must be explicit for VPS."
}

if ($values["CORS_ORIGINS"].Contains("*")) {
  throw "CORS_ORIGINS must be explicit for VPS."
}

Write-Host "OK VPS preflight: required env values are present and non-placeholder."
Write-Host "Next: docker compose --env-file $EnvFile -f docker-compose.vps.yml config"
