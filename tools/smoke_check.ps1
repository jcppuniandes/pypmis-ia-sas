param(
  [string]$ApiUrl = "http://localhost:8000",
  [string]$FrontendUrl = "http://localhost:5173",
  [int]$TenantId = 1,
  [string]$Email = "ana.control@demo.local",
  [string]$Password = "demo123"
)

$ErrorActionPreference = "Stop"

$health = Invoke-RestMethod -Uri "$ApiUrl/api/v1/health"
if ($health.status -ne "ok") {
  throw "API health check failed."
}

$ready = Invoke-RestMethod -Uri "$ApiUrl/api/v1/health/ready"
if ($ready.status -ne "ready") {
  throw "API readiness check failed."
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

$costManager = Invoke-RestMethod -Uri "$ApiUrl/api/v1/projects/$projectId/cost-manager-summary" -Headers $headers
if ($costManager.total_bac -lt 1) {
  throw "Cost Manager summary did not return BAC."
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
Write-Host "OK Readiness: $($ready.status)"
Write-Host "OK Authenticated user: $($session.user.email)"
Write-Host "OK Projects: $($projects.Count)"
Write-Host "OK Dashboard: $($dashboard.project.code)"
Write-Host "OK Cost Manager: BAC $($costManager.total_bac) / Funding $($costManager.total_funding)"
Write-Host "OK Pilot readiness: $($pilotReadiness.status) $($pilotReadiness.score)%"
Write-Host "OK Frontend: HTTP $($frontend.StatusCode)"
