param(
  [string]$ApiUrl = "http://localhost:8000",
  [int]$TenantId = 1,
  [string]$Email = "ana.control@demo.local",
  [string]$Password = "1234"
)

$ErrorActionPreference = "Stop"

$session = Invoke-RestMethod -Method Post -Uri "$ApiUrl/api/v1/auth/login" -ContentType "application/json" -Body (@{
  email = $Email
  password = $Password
  tenant_id = $TenantId
} | ConvertTo-Json)

$headers = @{
  Authorization = "Bearer $($session.access_token)"
}

$projects = Invoke-RestMethod -Uri "$ApiUrl/api/v1/projects" -Headers $headers
if ($projects.Count -eq 0) {
  throw "No projects available for $Email."
}

foreach ($project in $projects) {
  $readiness = Invoke-RestMethod -Uri "$ApiUrl/api/v1/projects/$($project.id)/pilot-readiness" -Headers $headers
  Write-Host ""
  Write-Host "$($project.code) - $($project.name)"
  Write-Host "Status: $($readiness.status) | Score: $($readiness.score)%"
  if ($readiness.blockers.Count -gt 0) {
    Write-Host "Blockers: $($readiness.blockers -join ', ')"
  }
  foreach ($item in $readiness.items) {
    Write-Host "[$($item.status)] $($item.phase) $($item.area): $($item.score)%"
    Write-Host "  Next: $($item.next_action)"
  }
}
