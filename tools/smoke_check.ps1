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

$frontend = Invoke-WebRequest -Uri $FrontendUrl -UseBasicParsing
if ($frontend.StatusCode -ne 200) {
  throw "Frontend health check failed."
}

Write-Host "OK API health: $($health.status)"
Write-Host "OK Authenticated user: $($session.user.email)"
Write-Host "OK Projects: $($projects.Count)"
Write-Host "OK Dashboard: $($dashboard.project.code)"
Write-Host "OK Frontend: HTTP $($frontend.StatusCode)"
