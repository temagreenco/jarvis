Param(
    [string]$BackupRoot = "F:\dev\backups",
    [string]$ProjectName = $env:COMPOSE_PROJECT_NAME,
    [string]$LogPath
)

if (-not $ProjectName) {
    $ProjectName = Split-Path (Get-Location) -Leaf
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $BackupRoot "jarvis\$timestamp"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

if (-not $LogPath) {
    $LogPath = Join-Path $backupDir "backup.log"
}

Start-Transcript -Path $LogPath | Out-Null
Write-Output "Backup started: $timestamp"
Write-Output "Project: $ProjectName"
Write-Output "Backup dir: $backupDir"

function Assert-Volume([string]$VolumeName) {
    docker volume inspect $VolumeName | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker volume not found: $VolumeName"
    }
}

function Backup-Volume([string]$VolumeName, [string]$ArchiveName) {
    Assert-Volume $VolumeName
    $archivePath = Join-Path $backupDir $ArchiveName
    docker run --rm -v "$VolumeName`:/data" -v "$backupDir`:/backup" alpine tar -czf "/backup/$ArchiveName" -C /data .
    if ($LASTEXITCODE -ne 0) {
        throw "Volume backup failed: $VolumeName"
    }
    Write-Output "Saved $archivePath"
}

$pgDumpPath = Join-Path $backupDir "postgres_dump.sql"
docker compose exec -T postgres sh -lc 'pg_dumpall -U "${POSTGRES_USER:-jarvis}"' | Out-File -FilePath $pgDumpPath -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    throw "Postgres dump failed"
}
Write-Output "Saved $pgDumpPath"

docker compose exec -T redis redis-cli SAVE | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Redis SAVE failed"
}

$postgresVolume = "${ProjectName}_postgres_data"
$redisVolume = "${ProjectName}_redis_data"
$minioVolume = "${ProjectName}_minio_data"

Backup-Volume $minioVolume "minio_data.tar.gz"
Backup-Volume $redisVolume "redis_data.tar.gz"

Write-Output "Backup finished"
Stop-Transcript | Out-Null
