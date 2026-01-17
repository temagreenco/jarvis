Param(
    [Parameter(Mandatory = $true)]
    [string]$BackupDir,
    [string]$ProjectName = $env:COMPOSE_PROJECT_NAME,
    [bool]$RestorePostgres = $true,
    [bool]$RestoreMinio = $true,
    [bool]$RestoreRedis = $true
)

$ErrorActionPreference = 'Stop'

if (-not $ProjectName) {
    $ProjectName = Split-Path (Get-Location) -Leaf
}

if (-not (Test-Path $BackupDir)) {
    throw "Backup directory not found: $BackupDir"
}

$pgDumpPath = Join-Path $BackupDir "postgres_dump.sql"
if ($RestorePostgres -and -not (Test-Path $pgDumpPath)) {
    throw "Postgres dump not found: $pgDumpPath"
}

function Restore-Volume([string]$VolumeName, [string]$ArchiveName) {
    $archivePath = Join-Path $BackupDir $ArchiveName
    if (-not (Test-Path $archivePath)) {
        throw "Archive not found: $archivePath"
    }
    docker run --rm -v "$VolumeName`:/data" -v "$BackupDir`:/backup" alpine sh -lc "rm -rf /data/* && tar -xzf /backup/$ArchiveName -C /data"
    if ($LASTEXITCODE -ne 0) {
        throw "Restore failed: $VolumeName"
    }
}

if ($RestoreMinio) {
    docker compose stop minio | Out-Null
    Restore-Volume "${ProjectName}_minio_data" "minio_data.tar.gz"
    docker compose start minio | Out-Null
}

if ($RestoreRedis) {
    docker compose stop redis | Out-Null
    Restore-Volume "${ProjectName}_redis_data" "redis_data.tar.gz"
    docker compose start redis | Out-Null
}

if ($RestorePostgres) {
    type "$pgDumpPath" | docker compose exec -T postgres psql -U jarvis
    if ($LASTEXITCODE -ne 0) {
        throw "Postgres restore failed"
    }
}

Write-Output "Restore complete."
