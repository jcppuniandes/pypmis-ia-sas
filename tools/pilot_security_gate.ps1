param(
  [string]$ApiUrl = "http://localhost:8000",
  [string]$FrontendUrl = "http://localhost:5173",
  [int]$TenantId = 1,
  [string]$PrimaryEmail = "ana.control@demo.local",
  [string]$SecondaryEmail = "laura.contracts@demo.local",
  [string]$Password = "demo123"
)

$ErrorActionPreference = "Stop"

Write-Host "== Pilot security gate =="

& "$PSScriptRoot\pilot_robust_gate.ps1" -ApiUrl $ApiUrl -FrontendUrl $FrontendUrl -TenantId $TenantId -Email $PrimaryEmail -Password $Password -RequireCtrlDemoReady

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
$authProviders = Invoke-RestMethod -Uri "$ApiUrl/api/v1/auth/providers"
if (-not $authProviders.local.enabled) {
  throw "Local auth provider is not enabled."
}
$ctrlDemo = $projects | Where-Object { $_.code -eq "CTRL-DEMO-001" } | Select-Object -First 1
$restrictedProject = $projects | Where-Object { $_.code -eq "REF-TURN-002" } | Select-Object -First 1
if ($null -eq $ctrlDemo -or $null -eq $restrictedProject) {
  throw "Expected pilot projects CTRL-DEMO-001 and REF-TURN-002 were not returned."
}

$restrictedStatus = 0
try {
  Invoke-WebRequest -Uri "$ApiUrl/api/v1/projects/$($restrictedProject.id)/document-attachments" -Headers $secondaryHeaders -UseBasicParsing | Out-Null
  throw "Secondary user unexpectedly listed restricted project attachments."
} catch {
  $restrictedStatus = [int]$_.Exception.Response.StatusCode
  if ($restrictedStatus -ne 403) {
    throw "Restricted project attachment list returned HTTP $restrictedStatus, expected 403."
  }
}

$attachments = Invoke-RestMethod -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/document-attachments" -Headers $primaryHeaders
$infected = $attachments | Where-Object { $_.scan_status -eq "infected" } | Select-Object -First 1
if ($null -ne $infected) {
  throw "Attachment $($infected.id) has unacceptable scan status: $($infected.scan_status)."
}
$pendingScanCount = @($attachments | Where-Object { $_.scan_status -eq "pending_scan" }).Count
$auditLogs = Invoke-RestMethod -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/audit-logs?limit=10" -Headers $primaryHeaders
if ($auditLogs.Count -lt 1) {
  throw "CTRL-DEMO-001 audit log endpoint returned no entries."
}

$restrictedAuditStatus = 0
try {
  Invoke-WebRequest -Uri "$ApiUrl/api/v1/projects/$($restrictedProject.id)/audit-logs" -Headers $secondaryHeaders -UseBasicParsing | Out-Null
  throw "Secondary user unexpectedly listed restricted project audit logs."
} catch {
  $restrictedAuditStatus = [int]$_.Exception.Response.StatusCode
  if ($restrictedAuditStatus -ne 403) {
    throw "Restricted project audit log returned HTTP $restrictedAuditStatus, expected 403."
  }
}

if ($attachments.Count -gt 0) {
  $attachment = $attachments | Select-Object -First 1
  $download = Invoke-WebRequest -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/documents/$($attachment.document_id)/attachments/$($attachment.id)/download" -Headers $primaryHeaders -UseBasicParsing
  if ($download.StatusCode -ne 200) {
    throw "Authenticated attachment download returned HTTP $($download.StatusCode)."
  }

  $anonymousStatus = 0
  try {
    Invoke-WebRequest -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/documents/$($attachment.document_id)/attachments/$($attachment.id)/download" -UseBasicParsing | Out-Null
    throw "Anonymous user unexpectedly downloaded an attachment."
  } catch {
    $anonymousStatus = [int]$_.Exception.Response.StatusCode
    if ($anonymousStatus -ne 401) {
      throw "Anonymous attachment download returned HTTP $anonymousStatus, expected 401."
    }
  }
  Write-Host "OK Authenticated attachment download protected: HTTP $($download.StatusCode)"
  Write-Host "OK Anonymous attachment download rejected: HTTP $anonymousStatus"
} else {
  Write-Host "WARN No CTRL-DEMO-001 attachments found; download protection check skipped."
}

Write-Host "OK Non-member restricted project attachments rejected: HTTP $restrictedStatus"
Write-Host "OK Auth providers endpoint: local=$($authProviders.local.enabled) oidc=$($authProviders.oidc.enabled)"
Write-Host "OK Attachment scan statuses acceptable / pending legacy: $pendingScanCount"
Write-Host "OK Audit log endpoint returned $($auditLogs.Count) entries"
Write-Host "OK Non-member restricted audit log rejected: HTTP $restrictedAuditStatus"
Write-Host "OK Pilot security gate completed"
