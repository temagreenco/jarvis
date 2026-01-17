param(
  [Parameter(Mandatory=$true)]
  [string]$RunDir,

  [string]$NoiseDb = "-35dB",
  [double]$MinSilence = 0.05
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $RunDir)) { throw "RunDir not found: $RunDir" }

$ffmpeg = "ffmpeg"
$ffprobe = "ffprobe"

$outCsv = Join-Path $RunDir "silence_report.csv"

$clips = Get-ChildItem -Path $RunDir -Filter "clip-*.mp4" | Sort-Object Name
if ($clips.Count -eq 0) { throw "No clips found in $RunDir" }

$rows = @()

foreach ($c in $clips) {
  $path = $c.FullName
  $name = $c.BaseName

  $durRaw = & $ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 "$path"
  $dur = [double]::Parse($durRaw, [System.Globalization.CultureInfo]::InvariantCulture)

$prev = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$log = & $ffmpeg -hide_banner -nostats -i "$path" -af "silencedetect=noise=$NoiseDb:d=$MinSilence" -f null - 2>&1
$ErrorActionPreference = $prev
  $lines = $log -split "`n"

  $events = @()
  foreach ($ln in $lines) {
    if ($ln -match "silence_start:\s*([0-9\.]+)") {
      $events += [pscustomobject]@{ type="start"; t=[double]$Matches[1] }
    } elseif ($ln -match "silence_end:\s*([0-9\.]+)\s*\|\s*silence_duration:\s*([0-9\.]+)") {
      $events += [pscustomobject]@{ type="end"; t=[double]$Matches[1]; d=[double]$Matches[2] }
    }
  }

  $leading = 0.0
  $firstStart = $events | Where-Object { $_.type -eq "start" } | Select-Object -First 1
  if ($firstStart -and [math]::Abs($firstStart.t) -lt 0.001) {
    $firstEnd = $events | Where-Object { $_.type -eq "end" } | Select-Object -First 1
    if ($firstEnd) { $leading = $firstEnd.t }
  }

  $trailing = 0.0
  $lastStart = $events | Where-Object { $_.type -eq "start" } | Select-Object -Last 1
  if ($lastStart -and ($dur - $lastStart.t) -lt 1.5) {
    $trailing = [math]::Max(0.0, $dur - $lastStart.t)
  }

  $startFlag =
    if ($leading -gt 0.20) { "TOO_EARLY(leading_silence)" }
    elseif ($leading -gt 0.06) { "OK_leadin" }
    elseif ($leading -gt 0.02) { "TIGHT" }
    else { "VERY_TIGHT_or_LATE" }

  $endFlag =
    if ($trailing -gt 0.35) { "TOO_MUCH_SILENCE" }
    elseif ($trailing -gt 0.10) { "OK_tail" }
    elseif ($trailing -gt 0.03) { "TIGHT" }
    else { "VERY_TIGHT_or_CHOPPED" }

  $rows += [pscustomobject]@{
    clip = $name
    duration_s = [math]::Round($dur, 3)
    leading_silence_s = [math]::Round($leading, 3)
    trailing_silence_s = [math]::Round($trailing, 3)
    start_flag = $startFlag
    end_flag = $endFlag
  }
}

$rows | Export-Csv -NoTypeInformation -Encoding UTF8 $outCsv
$rows | Format-Table -AutoSize

Write-Host ""
Write-Host "✅ Silence report saved: $outCsv"
