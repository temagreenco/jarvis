param(
  [Parameter(Mandatory=$true)]
  [string]$RunDir
)

$ErrorActionPreference = "Stop"

$manifest = Get-ChildItem -Path $RunDir -Filter "*.json" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $manifest) { throw "No manifest json found in $RunDir" }

$data = Get-Content $manifest.FullName -Raw | ConvertFrom-Json
if (-not $data.clips) { throw "Manifest has no 'clips' field: $($manifest.FullName)" }

$rows = @()

foreach ($c in $data.clips) {
  $start = [double]$c.start
  $end = [double]$c.end
  $dur = $end - $start

  $ss = $null
  $se = $null

  if ($c.PSObject.Properties.Name -contains "snapped_start") { $ss = [double]$c.snapped_start }
  if ($c.PSObject.Properties.Name -contains "snapped_end")   { $se = [double]$c.snapped_end }

  $dStart = if ($ss -ne $null) { $ss - $start } else { $null }
  $dEnd   = if ($se -ne $null) { $se - $end } else { $null }

  $rows += [pscustomobject]@{
    id = $c.id
    start = [math]::Round($start, 3)
    end   = [math]::Round($end, 3)
    dur_s = [math]::Round($dur, 3)
    snapped_start = if ($ss -ne $null) { [math]::Round($ss, 3) } else { "" }
    snapped_end   = if ($se -ne $null) { [math]::Round($se, 3) } else { "" }
    delta_start_s = if ($dStart -ne $null) { [math]::Round($dStart, 3) } else { "" }
    delta_end_s   = if ($dEnd -ne $null) { [math]::Round($dEnd, 3) } else { "" }
  }
}

$rows | Sort-Object id | Format-Table -AutoSize
