Param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,
    [string]$ObjectKey = "inputs/sample.mp4",
    [string]$ApiBase = "http://localhost:8000",
    [string]$Mode = "accurate",
    [bool]$SnapToSilence = $false,
    [double]$SnapWindowSec = 1.0
)

if (-not (Test-Path $InputPath)) {
    throw "Input file not found: $InputPath"
}

$minioUser = $(if ($Env:MINIO_ROOT_USER) { $Env:MINIO_ROOT_USER } else { "minioadmin" })
$minioPass = $(if ($Env:MINIO_ROOT_PASSWORD) { $Env:MINIO_ROOT_PASSWORD } else { "minioadmin" })
$minioBucket = $(if ($Env:MINIO_BUCKET) { $Env:MINIO_BUCKET } else { "jarvis" })
$mcHostLocal = "http://$minioUser`:$minioPass@minio:9000"

$inputFull = (Resolve-Path $InputPath).Path
$inputDir = Split-Path $inputFull -Parent
$inputFile = Split-Path $inputFull -Leaf

docker compose run --rm -e MC_HOST_local=$mcHostLocal -v "$inputDir`:/work" minio-mc cp "/work/$inputFile" "local/$minioBucket/$ObjectKey"

$segments = @(
    @{ id = "seg-1"; start = 0.0; end = 3.0 },
    @{ id = "seg-2"; start = 3.0; end = 6.0 }
)

$payload = @{
    input_s3_key = $ObjectKey
    mode = $Mode
    snap_to_silence = $SnapToSilence
    snap_window_sec = $SnapWindowSec
    segments = $segments
    metadata = @{ test = $true }
} | ConvertTo-Json -Depth 5

$job = Invoke-RestMethod -Method Post -Uri "$ApiBase/jobs" -ContentType "application/json" -Body $payload
$jobId = $job.id
Write-Output "Job created: $jobId"

for ($i = 0; $i -lt 20; $i++) {
    $status = Invoke-RestMethod -Method Get -Uri "$ApiBase/jobs/$jobId"
    if ($status.status -eq "completed" -or $status.status -eq "failed") {
        break
    }
    Start-Sleep -Seconds 1
}

$status = Invoke-RestMethod -Method Get -Uri "$ApiBase/jobs/$jobId"
if ($status.status -ne "completed") {
    throw "Job failed or timed out. Status: $($status.status)"
}

Invoke-WebRequest -Uri $status.links.output -OutFile "manifest.json" -ErrorAction Stop
Write-Output "Downloaded manifest to manifest.json"
