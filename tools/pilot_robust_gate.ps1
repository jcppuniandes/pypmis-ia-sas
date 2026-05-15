param(
  [string]$ApiUrl = "http://localhost:8000",
  [string]$FrontendUrl = "http://localhost:5173",
  [int]$TenantId = 1,
  [string]$Email = "ana.control@demo.local",
  [string]$Password = "1234",
  [double]$MinPilotScore = 90,
  [switch]$RequireCtrlDemoReady
)

$ErrorActionPreference = "Stop"

Write-Host "== Pilot robust gate =="
Write-Host "API: $ApiUrl"
Write-Host "Frontend: $FrontendUrl"

& "$PSScriptRoot\smoke_check.ps1" -ApiUrl $ApiUrl -FrontendUrl $FrontendUrl -TenantId $TenantId -Email $Email -Password $Password

$session = Invoke-RestMethod -Method Post -Uri "$ApiUrl/api/v1/auth/login" -ContentType "application/json" -Body (@{
  email = $Email
  password = $Password
  tenant_id = $TenantId
} | ConvertTo-Json)

$headers = @{
  Authorization = "Bearer $($session.access_token)"
}

$projects = Invoke-RestMethod -Uri "$ApiUrl/api/v1/projects" -Headers $headers
$ctrlDemo = $projects | Where-Object { $_.code -eq "CTRL-DEMO-001" } | Select-Object -First 1
if ($null -eq $ctrlDemo) {
  throw "CTRL-DEMO-001 was not returned for $Email."
}

$dashboard = Invoke-RestMethod -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/dashboard" -Headers $headers
if ($null -eq $dashboard.document_attachments) {
  throw "Dashboard response does not include document_attachments."
}
if ($null -eq $dashboard.cost_manager_summary -or $dashboard.cost_sheet.Count -lt 1) {
  throw "Dashboard does not include Cost Manager data."
}
if ($null -eq $dashboard.rfq_summary -or $dashboard.rfq_summary.total_packages -lt 1) {
  throw "Dashboard does not include RFQ data."
}

$attachments = Invoke-RestMethod -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/document-attachments" -Headers $headers
if ($attachments.Count -gt 0) {
  $invalidAttachment = $attachments | Where-Object { -not $_.sha256 -or $_.size_bytes -le 0 } | Select-Object -First 1
  if ($null -ne $invalidAttachment) {
    throw "At least one document attachment is missing sha256 or size metadata."
  }
}

$readiness = Invoke-RestMethod -Uri "$ApiUrl/api/v1/projects/$($ctrlDemo.id)/pilot-readiness" -Headers $headers
if ($readiness.score -lt $MinPilotScore) {
  throw "CTRL-DEMO-001 readiness $($readiness.score)% is below minimum $MinPilotScore%."
}
if ($RequireCtrlDemoReady -and $readiness.status -ne "ready") {
  throw "CTRL-DEMO-001 status is $($readiness.status), expected ready."
}

Write-Host "OK CTRL-DEMO-001 readiness: $($readiness.status) $($readiness.score)%"
Write-Host "OK Dashboard attachments contract: $($dashboard.document_attachments.Count) files"
Write-Host "OK Document attachment endpoint: $($attachments.Count) files"
Write-Host "OK Pilot robust gate completed"
