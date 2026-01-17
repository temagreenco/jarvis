Param(
    [Parameter(Mandatory = $true)]
    [string]$JobId,
    [string]$ApiBase = "http://localhost:8000",
    [string]$OutFile = "manifest.json"
)

$job = Invoke-RestMethod -Method Get -Uri "$ApiBase/jobs/$JobId"
if (-not $job.links -or -not $job.links.output) {
    throw "Job has no output link yet. Status: $($job.status)"
}

Invoke-WebRequest -Uri $job.links.output -OutFile $OutFile -ErrorAction Stop
Write-Output "Downloaded manifest to $OutFile"
