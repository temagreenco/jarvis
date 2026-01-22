Param(
    [switch]$Gpu,
    [string]$ApiUrl = "http://localhost:8000/health"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-Command($name) {
    return $null -ne (Get-Command $name -ErrorAction SilentlyContinue)
}

function Test-PortFree($port) {
    try {
        $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $port)
        $listener.Start()
        $listener.Stop()
        return $true
    } catch {
        return $false
    }
}

if (-not (Test-Command "docker")) {
    Write-Output "docker not found"
    exit 1
}

try {
    docker version | Out-Null
    docker compose version | Out-Null
    Write-Output "docker_ok=true"
} catch {
    Write-Output "docker_ok=false"
    exit 1
}

$ports = 8000, 9000, 9001, 6379, 5432
foreach ($port in $ports) {
    $free = Test-PortFree $port
    Write-Output ("port_{0}_free={1}" -f $port, $free)
}

if ($Gpu) {
    $gpuOk = Test-Command "nvidia-smi"
    Write-Output ("nvidia_smi_present={0}" -f $gpuOk)
    try {
        $runtimes = docker info --format '{{json .Runtimes}}'
        Write-Output ("docker_runtimes={0}" -f $runtimes)
    } catch {
        Write-Output "docker_runtimes=unavailable"
    }
}

$apiOk = $false
try {
    $resp = Invoke-WebRequest -Uri $ApiUrl -UseBasicParsing -TimeoutSec 5
    $apiOk = $resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300
} catch {
    $apiOk = $false
}

if (-not $apiOk) {
    foreach ($fallback in @("http://localhost:8000/docs", "http://localhost:8000/")) {
        try {
            $resp = Invoke-WebRequest -Uri $fallback -UseBasicParsing -TimeoutSec 5
            $apiOk = $resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300
            if ($apiOk) { break }
        } catch {
            $apiOk = $false
        }
    }
}

Write-Output ("api_reachable={0}" -f $apiOk)
