# Restart the Sentinel backend on port 8001 and PROVE it is the review-lock build.
#
#   powershell -ExecutionPolicy Bypass -File scripts\restart-8001.ps1
#
# 1. Force-kills every process listening on TCP 8001 (the usual reason an old
#    build keeps answering: the new server dies with "Address already in use"
#    and nobody notices).
# 2. Starts backend\server.py.
# 3. Polls /api/health until it reports
#       "build": "sentinel-fingerprint-review-lock-12h"
#       "review_lock_active": true
#    and fails loudly if it never does.
#
# Optional: -Port 8005   -NoStart (kill + verify only)

param(
    [int]$Port = 8001,
    [switch]$NoStart
)

$ErrorActionPreference = 'Continue'
$RequiredBuild = 'sentinel-fingerprint-review-lock-12h'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Server   = Join-Path $RepoRoot 'backend\server.py'

function Stop-PortListener {
    param([int]$TargetPort)
    $killed = @()
    $conns = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        $pid = $c.OwningProcess
        if ($pid -and $pid -ne $PID) {
            $name = (Get-Process -Id $pid -ErrorAction SilentlyContinue).ProcessName
            Write-Host "  killing pid $pid ($name) on port $TargetPort" -ForegroundColor Yellow
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            $killed += $pid
        }
    }
    if (-not $killed) { Write-Host "  nothing was listening on port $TargetPort" }
    return $killed
}

function Test-RequiredBuild {
    param([int]$TargetPort)
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$TargetPort/api/health" -TimeoutSec 5
    } catch {
        return $null
    }
    return $r
}

Write-Host "== 1. kill anything listening on port $Port ==" -ForegroundColor Cyan
Stop-PortListener -TargetPort $Port
Start-Sleep -Seconds 1

if ($NoStart) {
    Write-Host "`n-NoStart given: not starting a server." -ForegroundColor Cyan
    exit 0
}

Write-Host "`n== 2. start backend\server.py ==" -ForegroundColor Cyan
$log = Join-Path $env:TEMP "sentinel-$Port.log"
$p = Start-Process -FilePath 'python' -ArgumentList @($Server) -WorkingDirectory $RepoRoot `
        -RedirectStandardOutput $log -RedirectStandardError "$log.err" -PassThru -WindowStyle Hidden
Write-Host "  started pid $($p.Id); logs: $log / $log.err"

Write-Host "`n== 3. verify /api/health on port $Port ==" -ForegroundColor Cyan
$ok = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    $health = Test-RequiredBuild -TargetPort $Port
    if ($null -ne $health) {
        if ($health.build -eq $RequiredBuild -and $health.review_lock_active -eq $true) {
            Write-Host ("  build                : " + $health.build) -ForegroundColor Green
            Write-Host ("  review_lock_active   : " + $health.review_lock_active) -ForegroundColor Green
            Write-Host ("  window hours         : " + $health.fingerprint_review_window_hours) -ForegroundColor Green
            Write-Host ("  pid / started        : " + $health.pid + " / " + $health.started_at)
            Write-Host "`nOK - the review lock build is live on port $Port." -ForegroundColor Green
            $ok = $true
        } else {
            Write-Host ("  STALE BUILD on port ${Port}: build=" + $health.build) -ForegroundColor Red
            Write-Host "  Expected '$RequiredBuild'. Kill pid $($health.pid) and retry." -ForegroundColor Red
        }
        break
    }
}
if (-not $ok) {
    Write-Host "`nFAILED: no correct build answered on port $Port." -ForegroundColor Red
    if (Test-Path "$log.err") { Get-Content "$log.err" -Tail 20 }
    exit 1
}

Write-Host "`n== 4. audit approvals made while the stale server was up ==" -ForegroundColor Cyan
& python (Join-Path $RepoRoot 'backend\audit_instant_approvals.py')
if ($LASTEXITCODE -eq 1) {
    Write-Host "`nThe applications above were approved before 12 hours had passed." -ForegroundColor Yellow
    Write-Host "Re-run the audit with --revert to put them back to Pending Review:" -ForegroundColor Yellow
    Write-Host "  python backend\audit_instant_approvals.py --revert"
}
