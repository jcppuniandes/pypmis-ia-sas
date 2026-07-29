param(
  [string]$ApiUrl = "http://localhost:8000",
  [string]$FrontendUrl = "http://localhost:5173",
  [int]$TenantId = 1,
  [string]$Email = "ana.control@demo.local",
  [string]$Password = "1234",
  [string]$MetricsToken = ""
)

$ErrorActionPreference = "Stop"

$healthResponse = Invoke-WebRequest -Uri "$ApiUrl/api/v1/health" -UseBasicParsing
$health = $healthResponse.Content | ConvertFrom-Json
if ($health.status -ne "ok") {
  throw "API health check failed."
}
if ([string]$healthResponse.Headers["X-Content-Type-Options"] -ne "nosniff") {
  throw "Security header X-Content-Type-Options is missing."
}
if ([string]$healthResponse.Headers["X-Frame-Options"] -ne "DENY") {
  throw "Security header X-Frame-Options is missing."
}

$live = Invoke-RestMethod -Uri "$ApiUrl/api/v1/health/live"
if ($live.status -ne "live") {
  throw "API liveness check failed."
}

$ready = Invoke-RestMethod -Uri "$ApiUrl/api/v1/health/ready"
if ($ready.status -ne "ready") {
  throw "API readiness check failed."
}

$metricsHeaders = @{}
if ($MetricsToken) {
  $metricsHeaders["X-Metrics-Token"] = $MetricsToken
}
$metrics = Invoke-WebRequest -Uri "$ApiUrl/api/v1/ops/metrics" -Headers $metricsHeaders -UseBasicParsing
if ($metrics.Content -notmatch "pypmis_http_requests_total") {
  throw "Metrics endpoint did not return the expected Prometheus counters."
}

$session = Invoke-RestMethod -Method Post -Uri "$ApiUrl/api/v1/auth/login" -ContentType "application/json" -Body (@{
  email = $Email
  password = $Password
  tenant_id = $TenantId
} | ConvertTo-Json)

$headers = @{
  Authorization = "Bearer $($session.access_token)"
}

$projects = Invoke-RestMethod -Uri "$ApiUrl/api/v1/projects" -Headers $headers
if ($projects.Count -lt 1) {
  throw "No projects were returned for tenant $TenantId and user $Email."
}

$projectId = $projects[0].id
$dashboard = Invoke-RestMethod -Uri "$ApiUrl/api/v1/projects/$projectId/dashboard" -Headers $headers
if ($null -eq $dashboard.project_kpi) {
  throw "Dashboard did not return project KPI data."
}
if ($null -eq $dashboard.cost_manager_summary -or $dashboard.cost_sheet.Count -lt 1) {
  throw "Dashboard did not return Cost Manager data."
}
if ($null -eq $dashboard.document_control_summary -or $dashboard.document_control_summary.total_documents -lt 1) {
  throw "Dashboard did not return Document Control data."
}

$costManager = Invoke-RestMethod -Uri "$ApiUrl/api/v1/projects/$projectId/cost-manager-summary" -Headers $headers
if ($costManager.total_bac -lt 1) {
  throw "Cost Manager summary did not return BAC."
}
if ($costManager.total_committed_cost -lt 1 -or $costManager.total_purchase_order_commitments -lt 1) {
  throw "Cost Manager summary did not return contract or purchase order commitments."
}
if ($costManager.total_incurred_from_payment_certificates -lt 1 -or $costManager.total_incurred_from_warehouse_receipts -lt 1) {
  throw "Cost Manager summary did not return incurred cost from payment certificates and warehouse receipts."
}
if ($dashboard.rfq_summary.total_packages -lt 1 -or $dashboard.rfq_summary.bids_received -lt 1) {
  throw "Dashboard did not return RFQ packages and bid evaluations."
}

$pilotReadiness = Invoke-RestMethod -Uri "$ApiUrl/api/v1/projects/$projectId/pilot-readiness" -Headers $headers
if ($pilotReadiness.score -lt 60) {
  throw "Pilot readiness score is too low: $($pilotReadiness.score)."
}

$frontend = Invoke-WebRequest -Uri $FrontendUrl -UseBasicParsing
if ($frontend.StatusCode -ne 200) {
  throw "Frontend health check failed."
}

Write-Host "OK API health: $($health.status)"
Write-Host "OK API liveness: $($live.status) / uptime $($live.uptime_seconds)s"
Write-Host "OK Readiness: $($ready.status)"
Write-Host "OK Observability: Prometheus metrics exposed"
Write-Host "OK Security headers: nosniff / DENY"
Write-Host "OK Authenticated user: $($session.user.email)"
Write-Host "OK Projects: $($projects.Count)"
Write-Host "OK Dashboard: $($dashboard.project.code)"
Write-Host "OK Cost Manager: BAC $($costManager.total_bac) / Actas $($costManager.total_incurred_from_payment_certificates) / Almacen $($costManager.total_incurred_from_warehouse_receipts) / Committed $($costManager.total_committed_cost) / Funding $($costManager.total_funding)"
Write-Host "OK RFQ: $($dashboard.rfq_summary.total_packages) packages / $($dashboard.rfq_summary.bids_received) bids / recommended $($dashboard.rfq_summary.recommended_bidder)"
Write-Host "OK Document Control: $($dashboard.document_control_summary.controlled_document_score)% controlled"
Write-Host "OK Pilot readiness: $($pilotReadiness.status) $($pilotReadiness.score)%"
Write-Host "OK Frontend: HTTP $($frontend.StatusCode)"
