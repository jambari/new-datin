# =============================================================================
# LEMI-018 raw data sync → stageof-jayapura.bmkg.go.id (Stasiun Geofisika Jayapura)
#
# Runs hourly on the LEMI PC (172.21.63.105). Asks the server which raw files it
# already has (/magnet/api/lemi/raw/), then uploads every local file from the last
# $DAYS days that is missing or larger locally (today's file keeps growing).
# Missed days are therefore caught up automatically on the next run.
#
# Server uses the files to compute the JYP K index itself (FMI method), so Jayapura
# does not depend on BMKG pusat for it. The rsync to BMKG pusat (upload.bat) is untouched.
#
# Setup (as Administrator):
#   1. Copy this file to C:\lemi_raw_sync\lemi_raw_sync.ps1
#   2. Put the LEMI_MONITOR_TOKEN (same as C:\LEMIMonitor) in C:\lemi_raw_sync\token.txt
#   3. schtasks /create /tn LEMIRawSync /sc hourly /st 00:05 /ru SYSTEM /rl HIGHEST /f ^
#        /tr "powershell -NoProfile -ExecutionPolicy Bypass -File C:\lemi_raw_sync\lemi_raw_sync.ps1"
# Manual check without uploading:  powershell -File lemi_raw_sync.ps1 -DryRun
# =============================================================================
param(
    [int]$Days = 30,
    [switch]$DryRun
)

# ── CONFIG ────────────────────────────────────────────────────────────────────
$API_URL   = "https://stageof-jayapura.bmkg.go.id/magnet/api/lemi/raw/"
$RAW_DIR   = "D:\lemi018"
$TOKEN     = (Get-Content "$PSScriptRoot\token.txt" -Raw).Trim()
$LOG_FILE  = "$PSScriptRoot\lemi_raw_sync.log"
$CURL      = "$env:SystemRoot\System32\curl.exe"
# The public name goes through Cloudflare, which this LAN cannot reach: pin it to .189.
$RESOLVE   = "stageof-jayapura.bmkg.go.id:443:36.91.166.189"
# ─────────────────────────────────────────────────────────────────────────────

function Write-Log {
    param([string]$Message)
    $line = "$(Get-Date -f 'yyyy-MM-dd HH:mm:ss') $Message"
    Write-Host $line
    try { Add-Content -Path $LOG_FILE -Value $line -ErrorAction SilentlyContinue } catch {}
}

# Keep the log small: drop it when it passes 5 MB.
if ((Test-Path $LOG_FILE) -and ((Get-Item $LOG_FILE).Length -gt 5MB)) {
    Move-Item $LOG_FILE "$LOG_FILE.old" -Force
}

try {
    $manifestJson = & $CURL -s -f --max-time 60 --resolve $RESOLVE -H "Authorization: Bearer $TOKEN" "$($API_URL)?days=$($Days + 1)"
    if ($LASTEXITCODE -ne 0) { throw "curl exit $LASTEXITCODE" }
    $server = ($manifestJson | ConvertFrom-Json).files
} catch {
    Write-Log "ERROR: manifest not available: $_"
    exit 1
}

$since = (Get-Date).ToUniversalTime().Date.AddDays(-$Days)
$files = Get-ChildItem -Path $RAW_DIR -File -Filter "*.txt" | Where-Object {
    $_.Name -match '^\d{4} \d{2} \d{2} \d{2} \d{2} \d{2}\.txt$' -and
    [datetime]::ParseExact($_.Name.Substring(0, 10), 'yyyy MM dd', $null) -ge $since
} | Sort-Object Name

$sent = 0; $failed = 0; $skipped = 0
foreach ($f in $files) {
    $remote = $server.PSObject.Properties[$f.Name]
    $remoteSize = if ($remote) { [int64]$remote.Value } else { -1 }
    if ($f.Length -le $remoteSize) { $skipped++; continue }

    if ($DryRun) {
        Write-Log "DRY-RUN would send $($f.Name) local=$($f.Length) server=$remoteSize"
        continue
    }
    # Copy first: LEMI keeps today's file open while writing.
    $tmp = Join-Path $env:TEMP $f.Name
    try {
        Copy-Item -LiteralPath $f.FullName -Destination $tmp -Force
        $resp = & $CURL -s -f --max-time 300 --resolve $RESOLVE -H "Authorization: Bearer $TOKEN" -F "file=@$tmp" $API_URL
        if ($LASTEXITCODE -ne 0) { throw "curl exit $LASTEXITCODE" }
        Write-Log "OK   $($f.Name) $($f.Length) bytes $resp"
        $sent++
    } catch {
        Write-Log "ERR  $($f.Name): $_"
        $failed++
    } finally {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    }
}
Write-Log "Done: sent=$sent failed=$failed up-to-date=$skipped (last $Days days)"
if ($failed -gt 0) { exit 2 }
