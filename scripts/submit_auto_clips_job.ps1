Param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,
    [string]$ObjectKey = "inputs/sample.mp4",
    [string]$ApiBase = "http://localhost:8000",
    [bool]$SnapToSilence = $true,
    [double]$SnapWindowSec = 1.0,
    [int]$MaxClips = 5,
    [double]$MinDuration = 12,
    [double]$MaxDuration = 45,
    [int]$MinSentences = 2,
    [int]$MaxSentences = 6,
    [double]$HookBias = 1.0,
    [double]$ScoreThreshold = 0.25,
    [string]$BoundaryMode = "word",
    [string]$RenderMode = "original",
    [string]$TrackMode = "none",
    [string]$MotionMode = "static",
    [double]$LookspaceRatio = 0,
    [string]$Preset
)

if (-not (Test-Path $InputPath)) {
    throw "Input file not found: $InputPath"
}

$presetFile = Join-Path (Get-Location) "jarvis_presets.json"
if ($Preset) {
    $preset = $null
    if (Test-Path $presetFile) {
        $presetData = Get-Content $presetFile -Raw | ConvertFrom-Json
        $preset = $presetData.presets | Where-Object { $_.preset_name -eq $Preset } | Select-Object -First 1
    }
    if (-not $preset) {
        $presetPath = Join-Path (Get-Location) ("presets\{0}.json" -f $Preset)
        if (Test-Path $presetPath) {
            $preset = Get-Content $presetPath -Raw | ConvertFrom-Json
        }
    }
    if (-not $preset) { throw "Preset not found: $Preset" }
    Write-Output "USING PRESET: $Preset"
    if ($preset.boundary_mode) { $BoundaryMode = $preset.boundary_mode }
    if ($preset.score_threshold -ne $null) { $ScoreThreshold = [double]$preset.score_threshold }
    if ($preset.snap_to_silence -ne $null) { $SnapToSilence = [bool]$preset.snap_to_silence }
    if ($preset.max_clips -ne $null) { $MaxClips = [int]$preset.max_clips }
    if ($preset.min_duration -ne $null) { $MinDuration = [double]$preset.min_duration }
    if ($preset.max_duration -ne $null) { $MaxDuration = [double]$preset.max_duration }
    if ($preset.min_sentences -ne $null) { $MinSentences = [int]$preset.min_sentences }
    if ($preset.max_sentences -ne $null) { $MaxSentences = [int]$preset.max_sentences }
    if ($preset.hook_bias -ne $null) { $HookBias = [double]$preset.hook_bias }
    if ($preset.render_mode) { $RenderMode = $preset.render_mode }
    if ($preset.track_mode) { $TrackMode = $preset.track_mode }
    if ($preset.motion_mode) { $MotionMode = $preset.motion_mode }
    if ($preset.lookspace_ratio -ne $null) { $LookspaceRatio = [double]$preset.lookspace_ratio }
}

$minioUser = $(if ($Env:MINIO_ROOT_USER) { $Env:MINIO_ROOT_USER } else { "minioadmin" })
$minioPass = $(if ($Env:MINIO_ROOT_PASSWORD) { $Env:MINIO_ROOT_PASSWORD } else { "minioadmin" })
$minioBucket = $(if ($Env:MINIO_BUCKET) { $Env:MINIO_BUCKET } else { "jarvis" })
$mcHostLocal = "http://$minioUser`:$minioPass@minio:9000"

$inputFull = (Resolve-Path $InputPath).Path
$inputDir = Split-Path $inputFull -Parent
$inputFile = Split-Path $inputFull -Leaf

docker compose run --rm -e MC_HOST_local=$mcHostLocal -v "$inputDir`:/work" minio-mc cp "/work/$inputFile" "local/$minioBucket/$ObjectKey"

$reelsOptions = @{
    target_w = 1080
    target_h = 1920
    sample_fps = 4
    smoothing = 0.95
    deadzone_px = 60
    max_pan_px_per_s = 90
    motion_mode = $MotionMode
    lookspace_ratio = $LookspaceRatio
    micro_motion = $true
    micro_amp_px = 6
    micro_period_s = 5.0
    micro_only_when_stable = $true
}
if ($RenderMode -eq "reels" -and $TrackMode -eq "none") {
    $TrackMode = "face"
}
if ($RenderMode -eq "reels" -and -not $MotionMode) {
    $MotionMode = "static"
}

$payload = @{
    task = "auto_clips"
    input_s3_key = $ObjectKey
    snap_to_silence = $SnapToSilence
    snap_window_sec = $SnapWindowSec
    boundary_mode = $BoundaryMode
    render_mode = $RenderMode
    track_mode = $TrackMode
    reels = $reelsOptions
    auto_clips = @{
        max_clips = $MaxClips
        min_duration = $MinDuration
        max_duration = $MaxDuration
        min_sentences = $MinSentences
        max_sentences = $MaxSentences
        hook_bias = $HookBias
        score_threshold = $ScoreThreshold
    }
    metadata = @{ test = $true }
} | ConvertTo-Json -Depth 5

$job = Invoke-RestMethod -Method Post -Uri "$ApiBase/jobs" -ContentType "application/json" -Body $payload
$jobId = $job.id
Write-Output "Job created: $jobId"

for ($i = 0; $i -lt 60; $i++) {
    $status = Invoke-RestMethod -Method Get -Uri "$ApiBase/jobs/$jobId"
    if ($status.status -eq "completed" -or $status.status -eq "failed") {
        break
    }
    Start-Sleep -Seconds 2
}

$status = Invoke-RestMethod -Method Get -Uri "$ApiBase/jobs/$jobId"
if ($status.status -ne "completed") {
    throw "Job failed or timed out. Status: $($status.status)"
}

Invoke-WebRequest -Uri $status.links.output -OutFile "manifest_auto.json" -ErrorAction Stop
Write-Output "Downloaded manifest to manifest_auto.json"

$manifest = Get-Content "manifest_auto.json" | ConvertFrom-Json
$above = @($manifest.selected | Where-Object { -not $_.low_confidence }).Count
$fallback = @($manifest.selected | Where-Object { $_.low_confidence }).Count
Write-Output "Picked: $($manifest.selected.Count) / above_threshold=$above / fallback=$fallback"
Write-Output "Selected clips summary:"
foreach ($clip in $manifest.selected) {
    $fw = ""
    $lw = ""
    if ($clip.first_word) { $fw = "$($clip.first_word.w)" }
    if ($clip.last_word) { $lw = "$($clip.last_word.w)" }
    $txt = $clip.clip_text
    if ($txt -and $txt.Length -gt 90) { $txt = $txt.Substring(0,90) + "..." }
    $reelsFlag = if ($clip.reels_enabled) { "yes" } else { "no" }
    Write-Output " - $($clip.id) $($clip.start)-$($clip.end) score=$($clip.score) $fw->$lw reels=$reelsFlag hook=$($clip.hook_sentence) text=$txt"
}
