# =============================================================================
# LEMI-018 watchdog for the LEMI PC (172.21.63.105)
#
# Runs every minute as SYSTEM. Judges the program by its data: it expects the LEMI time
# to be the PC time minus the measured LEMI-PC difference, and if the last sample in the
# newest raw file is older than that by $StaleMinutes, lemi018.exe is hung or closed, so
# it is closed and started again through the interactive task LEMIStartProgram (the
# program has a window, so it must run in the logged-in bmkgs session).
#
# Limits: at most one restart per $CooldownMinutes. After $MaxRestarts restarts within
# an hour without fresh data, a restart will not help (sensor, cable, COM port), so it
# stops restarting and tells the site once, which alerts the Telegram group.
#
# The difference is measured again whenever a new sample appears, never fixed: the LEMI
# clock can lag the PC (8.4 minutes on 2026-11-01, which caused 79 needless restarts in a
# day when the two were compared directly) and it changes when either clock is corrected.
# A difference above $ClockWarnSeconds is logged as a clock warning.
#
# While the data is fresh it reports status ok every $OkEveryMinutes, because the site
# shows monitor_offline after 5 minutes without a report. Only failures of this routine
# report are logged. Telegram is unaffected: the site alerts only on a change from ok.
#
# Maintenance: create C:\lemi_watchdog\PAUSE to stop it; it is ignored after 12 hours
# so a forgotten file cannot disable the watchdog for good.
#
# Log: C:\lemi_watchdog\lemi_watchdog.log. See docs/kindex-jyp.md for installation.
# Observe only, closing nothing:  powershell -File lemi_watchdog.ps1 -DryRun
# =============================================================================
param(
    [switch]$DryRun,
    [switch]$NoNotify,
    [string]$RawDir = "D:\lemi018",
    [string]$ProcessName = "lemi018",
    [string]$StartTask = "LEMIStartProgram",
    [string]$StateDir = "C:\lemi_watchdog",
    [int]$StaleMinutes = 5,
    [int]$GraceMinutes = 5,
    [int]$CooldownMinutes = 10,
    [int]$MaxRestarts = 3,
    [int]$ClockWarnSeconds = 120,
    [int]$OkEveryMinutes = 4
)

$API_URL  = "https://stageof-jayapura.bmkg.go.id/magnet/api/instrument/status/"
$RESOLVE  = "stageof-jayapura.bmkg.go.id:443:36.91.166.189"
$TOKEN_FILE = "C:\lemi_raw_sync\token.txt"
$LOG_FILE = Join-Path $StateDir "lemi_watchdog.log"
$STATE_FILE = Join-Path $StateDir "state.json"
$PAUSE_FILE = Join-Path $StateDir "PAUSE"
$now = (Get-Date).ToUniversalTime()

function Write-Log {
    param([string]$Message)
    $line = "$($now.ToString('yyyy-MM-dd HH:mm:ss')) UTC $Message"
    Write-Host $line
    try { Add-Content -Path $LOG_FILE -Value $line -ErrorAction SilentlyContinue } catch {}
}

function Get-LastSample {
    # Read the file itself: directory size and time can lag while LEMI holds it open.
    $file = Get-ChildItem -Path $RawDir -File -Filter "*.txt" |
        Where-Object { $_.Name -match '^\d{4} \d{2} \d{2} \d{2} \d{2} \d{2}\.txt$' } |
        Sort-Object CreationTimeUtc, Name | Select-Object -Last 1   # a clock set back breaks name order
    if (-not $file) { return $null }
    $stream = New-Object IO.FileStream($file.FullName, 'Open', 'Read', 'ReadWrite,Delete')
    try {
        $size = [Math]::Min(400, $stream.Length)
        [void]$stream.Seek(-$size, 'End')
        $bytes = New-Object byte[] $size
        $read = $stream.Read($bytes, 0, $size)
    } finally { $stream.Close() }
    $lines = [Text.Encoding]::ASCII.GetString($bytes, 0, $read) -split "`n"
    [array]::Reverse($lines)
    foreach ($line in $lines) {
        if ($line -match '^(\d{4}) (\d{2}) (\d{2}) (\d{2}) (\d{2}) (\d{2})\s') {
            return New-Object DateTime ([int]$Matches[1], [int]$Matches[2], [int]$Matches[3],
                [int]$Matches[4], [int]$Matches[5], [int]$Matches[6], [DateTimeKind]::Utc)
        }
    }
    return $null
}

function Send-Status {
    param([string]$Status, [switch]$Quiet)
    if ($NoNotify) { Write-Log "(no-notify) status $Status"; return $true }
    $body = Join-Path $StateDir "status.json"
    Set-Content -Path $body -Encoding Ascii -Value ('{"instrument":"lemi","status":"' + $Status + '","computer_name":"' + $env:COMPUTERNAME + '"}')
    $token = (Get-Content $TOKEN_FILE -Raw).Trim()
    & "$env:SystemRoot\System32\curl.exe" -s -f --max-time 30 --resolve $RESOLVE -H "Authorization: Bearer $token" -H "Content-Type: application/json" --data-binary "@$body" $API_URL | Out-Null
    $ok = ($LASTEXITCODE -eq 0)
    Remove-Item $body -Force -ErrorAction SilentlyContinue
    if (-not $Quiet -or -not $ok) { Write-Log "status $Status sent=$ok" }
    return $ok
}

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
if ((Test-Path $LOG_FILE) -and ((Get-Item $LOG_FILE).Length -gt 5MB)) { Move-Item $LOG_FILE "$LOG_FILE.old" -Force }

if (-not (Test-Path $RawDir)) { Write-Log "ERROR: $RawDir not available, doing nothing"; exit 1 }
if ((Test-Path $PAUSE_FILE) -and (((Get-Date) - (Get-Item $PAUSE_FILE).LastWriteTime).TotalHours -lt 12)) {
    Write-Log "paused by $PAUSE_FILE"; exit 0
}

$state = @{ restarts = @(); alerted = $false; lastSample = $null; clockOffset = $null; lastOkSent = $null }
if (Test-Path $STATE_FILE) {
    try {
        $saved = Get-Content $STATE_FILE -Raw | ConvertFrom-Json
        $state.restarts = @($saved.restarts | Where-Object { $_ })
        $state.alerted = [bool]$saved.alerted
        $state.lastSample = $saved.lastSample
        $state.clockOffset = $saved.clockOffset
        $state.lastOkSent = $saved.lastOkSent
    } catch { Write-Log "state file unreadable, starting clean" }
}
function Save-State { $state | ConvertTo-Json | Set-Content -Path $STATE_FILE -Encoding Ascii }

$last = Get-LastSample
$lastText = if ($last) { $last.ToString('yyyy-MM-dd HH:mm:ss') } else { 'none' }
# Sample changed: the data is flowing, so measure the LEMI-PC difference now.
if ($last -and ($lastText -ne $state.lastSample -or $null -eq $state.clockOffset)) {
    $state.lastSample = $lastText
    $state.clockOffset = [Math]::Round(($now - $last).TotalSeconds, 1)
    Save-State
}
# Age = PC time minus the difference (expected LEMI time) minus the last sample.
$age = if ($last) { ($now.AddSeconds(-[double]$state.clockOffset) - $last).TotalMinutes } else { [double]::PositiveInfinity }
$procs = @(Get-Process -Name $ProcessName -ErrorAction SilentlyContinue)

if ($age -le $StaleMinutes) {
    if ($state.restarts.Count -gt 0 -or $state.alerted) {
        Write-Log "data fresh again, last sample $($last.ToString('HH:mm:ss')) after $($state.restarts.Count) restart(s)"
        if ($state.alerted -and (Send-Status 'ok')) { $state.lastOkSent = $now.ToString('o') }
        $state.restarts = @(); $state.alerted = $false
        Save-State
    } elseif ($now.Minute -eq 0) {
        $lag = if ($last) { [int]($now - $last).TotalSeconds } else { 0 }
        if ([Math]::Abs($lag) -gt $ClockWarnSeconds) {
            Write-Log "ok, last sample $lastText, CLOCK WARNING: LEMI differs from PC by $lag s"
        } else {
            Write-Log "ok, last sample $($last.ToString('HH:mm:ss'))"
        }
    }
    # Half a minute of slack: the task's start time jitters, and a report skipped by a
    # few seconds would come a minute late, on the limit of the site's 5 minutes.
    $due = (-not $state.lastOkSent) -or
        (($now - [datetime]::Parse($state.lastOkSent).ToUniversalTime()).TotalMinutes -ge ($OkEveryMinutes - 0.5))
    if ($due -and -not $DryRun -and (Send-Status 'ok' -Quiet)) {
        $state.lastOkSent = $now.ToString('o')
        Save-State
    }
    exit 0
}

# A program that has only just started (boot, or an operator restart) gets time to begin.
$young = @($procs | Where-Object { ((Get-Date) - $_.StartTime).TotalMinutes -lt $GraceMinutes })
if ($young.Count -gt 0) { Write-Log "stale ($lastText) but program started recently, waiting"; exit 0 }

$recent = @($state.restarts | Where-Object { ($now - [datetime]::Parse($_).ToUniversalTime()).TotalMinutes -lt 60 })
$state.restarts = $recent

if ($recent.Count -ge $MaxRestarts) {
    if (-not $state.alerted) {
        Write-Log "still stale after $($recent.Count) restarts in an hour, stopped restarting; operator needed (last sample $lastText)"
        if ($DryRun) { Write-Log "DRY-RUN would alert" }
        else {
            $status = if ($procs.Count -gt 0) { 'not_responding' } else { 'not_running' }
            $state.alerted = Send-Status $status
        }
    }
    Save-State
    exit 0
}
if ($recent.Count -gt 0) {
    $since = ($now - [datetime]::Parse($recent[-1]).ToUniversalTime()).TotalMinutes
    if ($since -lt $CooldownMinutes) { Write-Log "stale ($lastText), waiting after last restart"; exit 0 }
}

if ($DryRun) {
    Write-Log "DRY-RUN would restart $ProcessName (last sample $lastText, running=$($procs.Count))"
    exit 0
}
Write-Log "RESTART ${ProcessName}: last sample $lastText, running=$($procs.Count)"
foreach ($p in $procs) {
    try { Stop-Process -Id $p.Id -Force -ErrorAction Stop; [void]$p.WaitForExit(15000) }
    catch { Write-Log "could not stop pid $($p.Id): $_" }
}
if ($StartTask) {
    & schtasks.exe /run /tn $StartTask | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Log "ERROR: could not run task $StartTask (is bmkgs logged in?)" }
}
$state.restarts = @($recent) + $now.ToString('o')
Save-State
