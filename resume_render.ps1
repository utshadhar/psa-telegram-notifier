$config = Get-Content -Raw -Path "$PSScriptRoot\config.json" | ConvertFrom-Json
$apiKey = $config.RENDER_API_KEY
$serviceId = $config.RENDER_SERVICE_ID

if (-not $apiKey -or -not $serviceId) {
    Write-Error "RENDER_API_KEY or RENDER_SERVICE_ID is not configured in config.json."
    Exit 1
}

Write-Output "Resuming Render Service $serviceId..."
$headers = @{
    "Authorization" = "Bearer $apiKey"
    "Accept" = "application/json"
}

try {
    $response = Invoke-WebRequest -Uri "https://api.render.com/v1/services/$serviceId/resume" -Method Post -Headers $headers -ErrorAction Stop
    Write-Output "Render service resumed successfully."
} catch {
    Write-Error "Failed to resume Render service: $_"
}
