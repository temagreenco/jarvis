Param(
    [Parameter(Mandatory = $true)]
    [string]$Source,
    [Parameter(Mandatory = $true)]
    [string]$Destination
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path $Source)) {
    throw "Source not found: $Source"
}

New-Item -ItemType Directory -Force -Path $Destination | Out-Null

$sourcePath = (Resolve-Path $Source).Path
$destPath = (Resolve-Path $Destination).Path

if ($sourcePath.ToLower().EndsWith(".zip")) {
    Expand-Archive -Path $sourcePath -DestinationPath $destPath -Force
} else {
    Copy-Item -Path $sourcePath -Destination $destPath -Recurse -Force
}

$required = @(
    "docker-compose.yml",
    "Dockerfile",
    "requirements.txt",
    "api",
    "workers",
    "modules",
    "jarvis_presets.json"
)

$missing = @()
foreach ($item in $required) {
    $path = Join-Path $destPath $item
    if (-not (Test-Path $path)) {
        $missing += $item
    }
}

if ($missing.Count -gt 0) {
    Write-Output "Missing required items:"
    $missing | ForEach-Object { Write-Output "- $_" }
    exit 1
}

Write-Output ("restore_complete={0}" -f $destPath)
