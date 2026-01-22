Param(
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$targets = @(
    "_debug\\run_*",
    "_debug\\transcripts\\*.tmp"
)

$items = @()
foreach ($pattern in $targets) {
    $items += Get-ChildItem -Path $pattern -Force -ErrorAction SilentlyContinue
}

if ($items.Count -eq 0) {
    Write-Output "no_targets_found=true"
    exit 0
}

foreach ($item in $items) {
    Write-Output ("target={0}" -f $item.FullName)
}

if (-not $Force) {
    Write-Output "dry_run=true"
    exit 0
}

foreach ($item in $items) {
    Remove-Item -Path $item.FullName -Recurse -Force
}

Write-Output "deleted=true"
