param(
  [string]$ApiUrl = "http://localhost:8000",
  [string]$FrontendUrl = "http://localhost:5173",
  [int]$TenantId = 1,
  [string]$PrimaryEmail = "ana.control@demo.local",
  [string]$SecondaryEmail = "laura.contracts@demo.local",
  [string]$Password = "1234"
)

$ErrorActionPreference = "Stop"

Write-Host "== Pilot integration gate =="

& "$PSScriptRoot\pilot_security_gate.ps1" -ApiUrl $ApiUrl -FrontendUrl $FrontendUrl -TenantId $TenantId -PrimaryEmail $PrimaryEmail -SecondaryEmail $SecondaryEmail -Password $Password

$primarySession = Invoke-RestMethod -Method Post -Uri "$ApiUrl/api/v1/auth/login" -ContentType "application/json" -Body (@{
  email = $PrimaryEmail
  password = $Password
  tenant_id = $TenantId
} | ConvertTo-Json)
$primaryHeaders = @{ Authorization = "Bearer $($primarySession.access_token)" }

$secondarySession = Invoke-RestMethod -Method Post -Uri "$ApiUrl/api/v1/auth/login" -ContentType "application/json" -Body (@{
  email = $SecondaryEmail
  password = $Password
  tenant_id = $TenantId
} | ConvertTo-Json)
$secondaryHeaders = @{ Authorization = "Bearer $($secondarySession.access_token)" }

$projects = Invoke-RestMethod -Uri "$ApiUrl/api/v1/projects" -Headers $primaryHeaders
$ctrlDemo = $projects | Where-Object { $_.code -eq "CTRL-DEMO-001" } | Select-Object -First 1
$restrictedProject = $projects | Where-Object { $_.code -eq "REF-TURN-002" } | Select-Object -First 1
if ($null -eq $ctrlDemo -or $null -eq $restrictedProject) {
  throw "Expected pilot projects CTRL-DEMO-001 and REF-TURN-002 were not returned."
}

$manifest = Invoke-RestMethod -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/integration-manifest" -Headers $primaryHeaders
$datasetKeys = @($manifest.datasets | ForEach-Object { $_.key })
foreach ($requiredDataset in @("cost_sheet", "funding_sources", "cash_flow", "documents", "document_attachments", "control_account_mappings")) {
  if ($datasetKeys -notcontains $requiredDataset) {
    throw "Integration manifest did not publish required dataset: $requiredDataset"
  }
}

$costDataset = $manifest.datasets | Where-Object { $_.key -eq "cost_sheet" } | Select-Object -First 1
if ($null -eq $costDataset -or $costDataset.row_count -lt 1) {
  throw "Integration manifest returned no cost_sheet rows for CTRL-DEMO-001."
}

$csv = Invoke-WebRequest -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/integration-export?dataset=cost_sheet&format=csv" -Headers $primaryHeaders -UseBasicParsing
if ($csv.StatusCode -ne 200) {
  throw "Cost sheet CSV export returned HTTP $($csv.StatusCode)."
}
if ($csv.Content -notmatch "control_account_code") {
  throw "Cost sheet CSV export is missing control_account_code header."
}

$jsonExport = Invoke-RestMethod -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/integration-export?dataset=document_attachments&format=json" -Headers $primaryHeaders
if ($jsonExport.dataset -ne "document_attachments") {
  throw "Document attachment JSON export returned unexpected dataset key: $($jsonExport.dataset)"
}
if ($jsonExport.row_count -ne @($jsonExport.rows).Count) {
  throw "Document attachment JSON export row_count does not match rows length."
}

$packagePath = Join-Path ([System.IO.Path]::GetTempPath()) "pypmis-integration-package-$([guid]::NewGuid().ToString('N')).zip"
$packageHash = ""
$packageDatasetCount = 0
try {
  $webClient = New-Object System.Net.WebClient
  $webClient.Headers.Add("Authorization", $primaryHeaders.Authorization)
  $webClient.DownloadFile("$ApiUrl/api/v1/projects/$($ctrlDemo.id)/integration-package?datasets=cost_sheet,documents&format=both", $packagePath)
  $packageHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $packagePath).Hash.ToLowerInvariant()
  $reportedPackageHash = $webClient.ResponseHeaders["X-Package-Sha256"]
  if ($reportedPackageHash -and $reportedPackageHash.ToLowerInvariant() -ne $packageHash) {
    throw "Integration package checksum mismatch: header=$reportedPackageHash file=$packageHash"
  }

  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $zip = [System.IO.Compression.ZipFile]::OpenRead($packagePath)
  try {
    $entries = @($zip.Entries | ForEach-Object { $_.FullName })
    foreach ($requiredEntry in @("package_manifest.json", "datasets/cost_sheet.csv", "datasets/cost_sheet.json", "datasets/documents.csv", "datasets/documents.json")) {
      if ($entries -notcontains $requiredEntry) {
        throw "Integration package is missing required entry: $requiredEntry"
      }
    }
    $manifestEntry = $zip.GetEntry("package_manifest.json")
    $reader = New-Object System.IO.StreamReader($manifestEntry.Open())
    try {
      $packageManifest = $reader.ReadToEnd() | ConvertFrom-Json
    } finally {
      $reader.Dispose()
    }
    if ($packageManifest.mode -ne "read_only") {
      throw "Integration package manifest mode is $($packageManifest.mode), expected read_only."
    }
    if ($packageManifest.format -ne "both") {
      throw "Integration package manifest format is $($packageManifest.format), expected both."
    }
    $packageDatasetCount = @($packageManifest.datasets).Count
    if ($packageDatasetCount -ne 2) {
      throw "Integration package manifest returned $packageDatasetCount datasets, expected 2."
    }
    if (@($packageManifest.files).Count -lt 4) {
      throw "Integration package manifest returned fewer than 4 files."
    }
  } finally {
    $zip.Dispose()
  }
} finally {
  if (Test-Path -LiteralPath $packagePath) {
    Remove-Item -LiteralPath $packagePath -Force
  }
}

$workbookPath = Join-Path ([System.IO.Path]::GetTempPath()) "pypmis-integration-workbook-$([guid]::NewGuid().ToString('N')).xlsx"
$workbookHash = ""
try {
  $webClient = New-Object System.Net.WebClient
  $webClient.Headers.Add("Authorization", $primaryHeaders.Authorization)
  $webClient.DownloadFile("$ApiUrl/api/v1/projects/$($ctrlDemo.id)/integration-workbook?datasets=cost_sheet,documents", $workbookPath)
  $workbookHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $workbookPath).Hash.ToLowerInvariant()
  $reportedWorkbookHash = $webClient.ResponseHeaders["X-Workbook-Sha256"]
  if ($reportedWorkbookHash -and $reportedWorkbookHash.ToLowerInvariant() -ne $workbookHash) {
    throw "Integration workbook checksum mismatch: header=$reportedWorkbookHash file=$workbookHash"
  }

  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $xlsx = [System.IO.Compression.ZipFile]::OpenRead($workbookPath)
  try {
    $workbookEntries = @($xlsx.Entries | ForEach-Object { $_.FullName })
    foreach ($requiredEntry in @("xl/workbook.xml", "xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml", "xl/styles.xml")) {
      if ($workbookEntries -notcontains $requiredEntry) {
        throw "Integration workbook is missing required entry: $requiredEntry"
      }
    }
    $workbookEntry = $xlsx.GetEntry("xl/workbook.xml")
    $reader = New-Object System.IO.StreamReader($workbookEntry.Open())
    try {
      $workbookXml = $reader.ReadToEnd()
    } finally {
      $reader.Dispose()
    }
    if ($workbookXml -notmatch "Summary" -or $workbookXml -notmatch "cost_sheet") {
      throw "Integration workbook did not include expected Summary and cost_sheet sheets."
    }
  } finally {
    $xlsx.Dispose()
  }
} finally {
  if (Test-Path -LiteralPath $workbookPath) {
    Remove-Item -LiteralPath $workbookPath -Force
  }
}

$tokenPayload = @{
  name = "Gate BI export token"
  datasets = @("cost_sheet", "documents")
  formats = @("json", "csv", "both", "xlsx")
  expires_in_days = 7
} | ConvertTo-Json
$integrationToken = Invoke-RestMethod -Method Post -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/integration-tokens" -Headers $primaryHeaders -ContentType "application/json" -Body $tokenPayload
if (-not $integrationToken.token.StartsWith("pypmis_it_")) {
  throw "Integration token did not use the governed token prefix."
}
$integrationHeaders = @{ Authorization = "Bearer $($integrationToken.token)" }
$tokenManifest = Invoke-RestMethod -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/integration-manifest" -Headers $integrationHeaders
$tokenDatasetKeys = @($tokenManifest.datasets | ForEach-Object { $_.key })
if ($tokenDatasetKeys.Count -ne 2 -or $tokenDatasetKeys -notcontains "cost_sheet" -or $tokenDatasetKeys -notcontains "documents") {
  throw "Integration token manifest scope is unexpected: $($tokenDatasetKeys -join ', ')"
}
$tokenPackage = Invoke-WebRequest -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/integration-package?datasets=cost_sheet,documents&format=both" -Headers $integrationHeaders -UseBasicParsing
if ($tokenPackage.StatusCode -ne 200 -or -not $tokenPackage.Headers["X-Package-Sha256"]) {
  throw "Integration token package request did not return a valid package response."
}
$tokenWorkbook = Invoke-WebRequest -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/integration-workbook?datasets=cost_sheet,documents" -Headers $integrationHeaders -UseBasicParsing
if ($tokenWorkbook.StatusCode -ne 200 -or -not $tokenWorkbook.Headers["X-Workbook-Sha256"]) {
  throw "Integration token workbook request did not return a valid workbook response."
}
$tokenForbiddenStatus = 0
try {
  Invoke-WebRequest -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/integration-export?dataset=funding_sources&format=json" -Headers $integrationHeaders -UseBasicParsing | Out-Null
  throw "Integration token unexpectedly exported an out-of-scope dataset."
} catch {
  $tokenForbiddenStatus = [int]$_.Exception.Response.StatusCode
  if ($tokenForbiddenStatus -ne 403) {
    throw "Out-of-scope integration token export returned HTTP $tokenForbiddenStatus, expected 403."
  }
}
$tokenList = Invoke-RestMethod -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/integration-tokens" -Headers $primaryHeaders
if (@($tokenList | Where-Object { $_.id -eq $integrationToken.id }).Count -lt 1) {
  throw "Created integration token was not returned by token list endpoint."
}
$tokenAlerts = Invoke-RestMethod -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/integration-token-alerts?warning_days=14" -Headers $primaryHeaders
$gateTokenAlert = $tokenAlerts.alerts | Where-Object { $_.id -eq $integrationToken.id } | Select-Object -First 1
if ($null -eq $gateTokenAlert) {
  throw "Integration token alert catalog did not flag the 7-day gate token."
}
if ($gateTokenAlert.severity -ne "warning" -or $gateTokenAlert.days_to_expiry -gt 14) {
  throw "Integration token alert severity was $($gateTokenAlert.severity) / $($gateTokenAlert.days_to_expiry) days, expected warning within 14 days."
}
$revokedToken = Invoke-RestMethod -Method Post -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/integration-tokens/$($integrationToken.id)/revoke" -Headers $primaryHeaders
if ($revokedToken.status -ne "revoked") {
  throw "Integration token revoke returned status $($revokedToken.status), expected revoked."
}
$revokedStatus = 0
try {
  Invoke-WebRequest -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/integration-export?dataset=cost_sheet&format=csv" -Headers $integrationHeaders -UseBasicParsing | Out-Null
  throw "Revoked integration token unexpectedly exported data."
} catch {
  $revokedStatus = [int]$_.Exception.Response.StatusCode
  if ($revokedStatus -ne 401) {
    throw "Revoked integration token returned HTTP $revokedStatus, expected 401."
  }
}

$downloadLogs = Invoke-RestMethod -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/integration-downloads?limit=25" -Headers $primaryHeaders
$downloadArtifactTypes = @($downloadLogs | ForEach-Object { $_.artifact_type })
foreach ($requiredArtifactType in @("export", "package", "workbook")) {
  if ($downloadArtifactTypes -notcontains $requiredArtifactType) {
    throw "Integration download catalog did not include artifact type: $requiredArtifactType"
  }
}
$workbookLog = $downloadLogs | Where-Object { $_.artifact_type -eq "workbook" -and $_.sha256 } | Select-Object -First 1
if ($null -eq $workbookLog) {
  throw "Integration download catalog did not include a workbook log with sha256."
}
$tokenDownloadLog = $downloadLogs | Where-Object { $_.integration_token_id -eq $integrationToken.id } | Select-Object -First 1
if ($null -eq $tokenDownloadLog) {
  throw "Integration download catalog did not include the token-generated artifact."
}

$restrictedStatus = 0
try {
  Invoke-WebRequest -Uri "$ApiUrl/api/v1/projects/$($restrictedProject.id)/integration-export?dataset=cost_sheet&format=csv" -Headers $secondaryHeaders -UseBasicParsing | Out-Null
  throw "Secondary user unexpectedly exported restricted project cost sheet."
} catch {
  $restrictedStatus = [int]$_.Exception.Response.StatusCode
  if ($restrictedStatus -ne 403) {
    throw "Restricted project integration export returned HTTP $restrictedStatus, expected 403."
  }
}

$restrictedPackageStatus = 0
try {
  Invoke-WebRequest -Uri "$ApiUrl/api/v1/projects/$($restrictedProject.id)/integration-package?datasets=cost_sheet&format=csv" -Headers $secondaryHeaders -UseBasicParsing | Out-Null
  throw "Secondary user unexpectedly generated restricted project integration package."
} catch {
  $restrictedPackageStatus = [int]$_.Exception.Response.StatusCode
  if ($restrictedPackageStatus -ne 403) {
    throw "Restricted project integration package returned HTTP $restrictedPackageStatus, expected 403."
  }
}

$restrictedWorkbookStatus = 0
try {
  Invoke-WebRequest -Uri "$ApiUrl/api/v1/projects/$($restrictedProject.id)/integration-workbook?datasets=cost_sheet" -Headers $secondaryHeaders -UseBasicParsing | Out-Null
  throw "Secondary user unexpectedly generated restricted project integration workbook."
} catch {
  $restrictedWorkbookStatus = [int]$_.Exception.Response.StatusCode
  if ($restrictedWorkbookStatus -ne 403) {
    throw "Restricted project integration workbook returned HTTP $restrictedWorkbookStatus, expected 403."
  }
}

$restrictedDownloadsStatus = 0
try {
  Invoke-WebRequest -Uri "$ApiUrl/api/v1/projects/$($restrictedProject.id)/integration-downloads" -Headers $secondaryHeaders -UseBasicParsing | Out-Null
  throw "Secondary user unexpectedly listed restricted project integration downloads."
} catch {
  $restrictedDownloadsStatus = [int]$_.Exception.Response.StatusCode
  if ($restrictedDownloadsStatus -ne 403) {
    throw "Restricted project integration downloads returned HTTP $restrictedDownloadsStatus, expected 403."
  }
}

$restrictedAlertsStatus = 0
try {
  Invoke-WebRequest -Uri "$ApiUrl/api/v1/projects/$($restrictedProject.id)/integration-token-alerts" -Headers $secondaryHeaders -UseBasicParsing | Out-Null
  throw "Secondary user unexpectedly listed restricted project integration token alerts."
} catch {
  $restrictedAlertsStatus = [int]$_.Exception.Response.StatusCode
  if ($restrictedAlertsStatus -ne 403) {
    throw "Restricted project integration token alerts returned HTTP $restrictedAlertsStatus, expected 403."
  }
}

$invalidStatus = 0
try {
  Invoke-WebRequest -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/integration-export?dataset=unknown&format=json" -Headers $primaryHeaders -UseBasicParsing | Out-Null
  throw "Unknown integration dataset was accepted unexpectedly."
} catch {
  $invalidStatus = [int]$_.Exception.Response.StatusCode
  if ($invalidStatus -ne 400) {
    throw "Unknown integration dataset returned HTTP $invalidStatus, expected 400."
  }
}

$invalidPackageStatus = 0
try {
  Invoke-WebRequest -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/integration-package?datasets=unknown&format=both" -Headers $primaryHeaders -UseBasicParsing | Out-Null
  throw "Unknown integration package dataset was accepted unexpectedly."
} catch {
  $invalidPackageStatus = [int]$_.Exception.Response.StatusCode
  if ($invalidPackageStatus -ne 400) {
    throw "Unknown integration package dataset returned HTTP $invalidPackageStatus, expected 400."
  }
}

$invalidWorkbookStatus = 0
try {
  Invoke-WebRequest -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/integration-workbook?datasets=unknown" -Headers $primaryHeaders -UseBasicParsing | Out-Null
  throw "Unknown integration workbook dataset was accepted unexpectedly."
} catch {
  $invalidWorkbookStatus = [int]$_.Exception.Response.StatusCode
  if ($invalidWorkbookStatus -ne 400) {
    throw "Unknown integration workbook dataset returned HTTP $invalidWorkbookStatus, expected 400."
  }
}

Write-Host "OK Integration manifest datasets: $($datasetKeys -join ', ')"
Write-Host "OK Cost sheet CSV export rows: $($costDataset.row_count)"
Write-Host "OK Document attachment JSON export rows: $($jsonExport.row_count)"
Write-Host "OK Integration package datasets: $packageDatasetCount / sha256 $packageHash"
Write-Host "OK Integration workbook sha256: $workbookHash"
Write-Host "OK Integration token scope: $($tokenDatasetKeys -join ', ')"
Write-Host "OK Integration token alert: $($gateTokenAlert.severity) / $($gateTokenAlert.days_to_expiry) days"
Write-Host "OK Integration token out-of-scope rejected: HTTP $tokenForbiddenStatus"
Write-Host "OK Revoked integration token rejected: HTTP $revokedStatus"
Write-Host "OK Integration download catalog artifacts: $($downloadArtifactTypes -join ', ')"
Write-Host "OK Integration download catalog token log: $($tokenDownloadLog.id)"
Write-Host "OK Non-member restricted integration export rejected: HTTP $restrictedStatus"
Write-Host "OK Non-member restricted integration package rejected: HTTP $restrictedPackageStatus"
Write-Host "OK Non-member restricted integration workbook rejected: HTTP $restrictedWorkbookStatus"
Write-Host "OK Non-member restricted integration downloads rejected: HTTP $restrictedDownloadsStatus"
Write-Host "OK Non-member restricted integration token alerts rejected: HTTP $restrictedAlertsStatus"
Write-Host "OK Unknown integration dataset rejected: HTTP $invalidStatus"
Write-Host "OK Unknown integration package dataset rejected: HTTP $invalidPackageStatus"
Write-Host "OK Unknown integration workbook dataset rejected: HTTP $invalidWorkbookStatus"
Write-Host "OK Pilot integration gate completed"
