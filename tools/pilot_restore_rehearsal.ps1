param(
  [string]$BackupDir,
  [string]$ContainerName = ""
)

$ErrorActionPreference = "Stop"

function Invoke-DockerChecked {
  param(
    [string[]]$Arguments
  )
  & docker @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Docker command failed ($LASTEXITCODE): docker $($Arguments -join ' ')"
  }
}

if (-not $BackupDir) {
  $latest = Get-ChildItem -Path ".\backups\pilot" -Directory -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if ($null -eq $latest) {
    throw "No backup directory was found under .\backups\pilot."
  }
  $BackupDir = $latest.FullName
}

$resolvedBackupDir = Resolve-Path -Path $BackupDir
$manifestPath = Join-Path $resolvedBackupDir "manifest.json"
if (-not (Test-Path $manifestPath)) {
  throw "manifest.json was not found in $resolvedBackupDir."
}

$manifest = Get-Content -Path $manifestPath -Raw | ConvertFrom-Json
$dbBackup = Join-Path $resolvedBackupDir $manifest.database_backup
if (-not (Test-Path $dbBackup)) {
  throw "Database backup was not found: $dbBackup"
}

if (-not $ContainerName) {
  $ContainerName = "pypmis-restore-rehearsal-$((Get-Date).ToString('yyyyMMddHHmmss'))"
}

Write-Host "== Pilot restore rehearsal =="
Write-Host "Backup: $resolvedBackupDir"
Write-Host "Temporary container: $ContainerName"

Invoke-DockerChecked @("run", "-d", "--name", $ContainerName, "-e", "POSTGRES_DB=pypmis_restore", "-e", "POSTGRES_USER=pypmis", "-e", "POSTGRES_PASSWORD=pypmis", "postgres:16-alpine")
$containerStarted = $true
try {
  $ready = $false
  for ($i = 0; $i -lt 30; $i++) {
    docker exec $ContainerName pg_isready -h 127.0.0.1 -U pypmis -d pypmis_restore | Out-Null
    if ($LASTEXITCODE -eq 0) {
      $ready = $true
      break
    }
    Start-Sleep -Seconds 1
  }
  if (-not $ready) {
    throw "Temporary PostgreSQL container did not become ready."
  }

  Invoke-DockerChecked @("cp", $dbBackup, "${ContainerName}:/tmp/restore.dump")
  Invoke-DockerChecked @("exec", $ContainerName, "pg_restore", "-h", "127.0.0.1", "-U", "pypmis", "-d", "pypmis_restore", "/tmp/restore.dump")
  $tableCount = docker exec $ContainerName psql -h 127.0.0.1 -U pypmis -d pypmis_restore -tAc "select count(*) from information_schema.tables where table_schema = 'public';"
  if ($LASTEXITCODE -ne 0) {
    throw "Could not query restored database."
  }
  $tableCount = $tableCount.Trim()
  if ([int]$tableCount -lt 1) {
    throw "Restore rehearsal finished with no public tables."
  }
  Write-Host "OK Restore rehearsal loaded $tableCount public tables"
} finally {
  if ($containerStarted) {
    docker rm -f $ContainerName | Out-Null
    if ($LASTEXITCODE -ne 0) {
      Write-Warning "Could not remove temporary restore container: $ContainerName"
    }
  }
}

Write-Host "OK Temporary restore container removed"
Write-Host "OK Pilot restore rehearsal completed"
