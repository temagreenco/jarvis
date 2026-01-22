Param(
    [string]$DestinationRoot = (Join-Path $PSScriptRoot "..\_backup")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm"
$backupDir = Join-Path $DestinationRoot ("backup_{0}" -f $timestamp)
$zipPath = Join-Path $DestinationRoot ("backup_{0}.zip" -f $timestamp)

New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

$paths = @(
    "docker-compose.yml",
    "docker-compose.cpu.yml",
    "docker-compose.external-redis.yml",
    "Dockerfile",
    "Dockerfile.cpu",
    "requirements.txt",
    "run.ps1",
    "run.sh",
    "scripts",
    "api",
    "workers",
    "modules",
    "config",
    "jarvis_presets.json",
    ".env.example",
    "README.md"
)

foreach ($item in $paths) {
    $src = Join-Path (Get-Location) $item
    if (Test-Path $src) {
        $dst = Join-Path $backupDir $item
        $dstDir = Split-Path $dst -Parent
        if (-not (Test-Path $dstDir)) {
            New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
        }
        Copy-Item -Path $src -Destination $dst -Recurse -Force
    }
}

$readme = @(
    "# Backup README",
    "",
    "This folder contains a snapshot of the Jarvis repo plus documentation and settings.",
    "",
    "Created: $timestamp",
    "",
    "Included:",
    "- docker compose files",
    "- Dockerfiles",
    "- Python modules and workers",
    "- scripts",
    "- presets and config",
    "",
    "See FIRST_RUN_CHECKLIST.md for setup and PIPELINE_SETTINGS.md for clip settings."
)
$readme | Set-Content -Encoding ASCII -Path (Join-Path $backupDir "BACKUP_README.md")

$checklist = @(
    "# First Run Checklist",
    "",
    "1) Install:",
    "- Docker Desktop (or Docker Engine) and Docker Compose",
    "- For GPU: NVIDIA driver and NVIDIA Container Toolkit",
    "",
    "2) Verify commands:",
    "- docker version",
    "- docker compose version",
    "",
    "3) Start services:",
    "- docker compose up -d --build",
    "",
    "4) Create MinIO bucket if needed:",
    "- scripts\\create_minio_buckets.ps1",
    "",
    "5) Submit an auto-clips job (example):",
    "- scripts\\submit_auto_clips_job.ps1 -InputPath <file> -TranscriptPath <file>",
    "",
    "6) Parameters to check (examples):",
    "- max_clips, min_duration, max_duration",
    "- min_sentences, max_sentences",
    "- boundary_mode, snap_to_silence",
    "- hook_first_cutting, hook_window_sec, hook_min_rms_db",
    "- language",
    "",
    "7) Outputs:",
    "- MinIO jobs/<job_id>/manifest.json",
    "- clips/clip-*.mp4 and clip-*_reels.mp4",
    "",
    "Troubleshooting:",
    "- MinIO bucket not found: run scripts\\create_minio_buckets.ps1",
    "- Containers in different Docker networks: ensure all services share the same network",
    "- Worker cannot reach postgres/redis: check env vars and service names in docker-compose.yml",
    "- container_name conflict: remove old containers or rename in docker-compose.yml",
    "- API connection closed: restart api and check logs",
    "- Health endpoint not found: try http://localhost:8000/docs"
)
$checklist | Set-Content -Encoding ASCII -Path (Join-Path $backupDir "FIRST_RUN_CHECKLIST.md")

$pipeline = @(
    "# Pipeline Settings",
    "",
    "Auto-clips tuning parameters:",
    "- max_clips",
    "- min_duration, max_duration",
    "- min_sentences, max_sentences",
    "- hook_bias, score_threshold",
    "- min_avg_word_confidence",
    "- diversity_radius_s",
    "- language",
    "- target_duration_sec",
    "- prefer_duration_min_sec",
    "- prefer_duration_max_sec",
    "- max_duration_sec",
    "- enable_extend_to_completion",
    "- sentence_max_gap",
    "- extend_silence_gap_sec",
    "",
    "Hook-first and loud start:",
    "- hook_first_cutting",
    "- hook_window_sec",
    "- hook_min_rms_db",
    "",
    "Boundary and snapping:",
    "- boundary_mode",
    "- snap_to_silence",
    "- snap_window_sec",
    "",
    "Reels rendering:",
    "- render_mode=reels",
    "- track_mode=face",
    "- reels options (target_w, target_h, sample_fps, smoothing, deadzone_px, max_pan_px_per_s)",
    "",
    "Presets:",
    "- reels_premium_hebrew",
    "- reels_premium_hebrew_long",
    "",
    "Note: If preset binding fails in scripts\\submit_auto_clips_job.ps1, pass the values explicitly."
)
$pipeline | Set-Content -Encoding ASCII -Path (Join-Path $backupDir "PIPELINE_SETTINGS.md")

$cleanup = @(
    "# Cleanup Guide",
    "",
    "Safe to delete:",
    "- _debug\\run_*",
    "- _debug\\transcripts\\*.tmp",
    "",
    "Delete only if you are sure:",
    "- model caches (if any)",
    "- docker volumes (removes DB and MinIO data)",
    "",
    "Do NOT delete:",
    "- modules\\",
    "- workers\\",
    "- api\\",
    "- scripts\\",
    "- jarvis_presets.json",
    "- docker-compose.yml",
    "",
    "Use scripts\\cleanup_safe.ps1 for a dry-run cleanup."
)
$cleanup | Set-Content -Encoding ASCII -Path (Join-Path $backupDir "CLEANUP_GUIDE.md")

$filesReport = Join-Path $backupDir "FILES_USED_REPORT.md"
if (-not (Test-Path $filesReport)) {
    "" | Set-Content -Encoding ASCII -Path $filesReport
}

$analyzeScript = Join-Path $PSScriptRoot "analyze_used_files.py"
if (Test-Path $analyzeScript) {
    $reportPath = Join-Path $backupDir "FILES_USED_REPORT.md"
    try {
        python $analyzeScript --repo (Get-Location) --output $reportPath | Out-Null
    } catch {
        "FILES_USED_REPORT could not be generated. Ensure Python is installed." | Set-Content -Encoding ASCII -Path $reportPath
    }
}

if (Test-Path $zipPath) {
    Remove-Item -Force $zipPath
}
Compress-Archive -Path $backupDir -DestinationPath $zipPath -Force

Write-Output ("backup_dir={0}" -f $backupDir)
Write-Output ("zip_path={0}" -f $zipPath)
