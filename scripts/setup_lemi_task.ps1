# setup_lemi_task.ps1
# Run once as Administrator on the Windows LEMI computer to register
# the monitoring script as a Task Scheduler job that starts at boot.
#
# Usage (in an elevated PowerShell):
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\setup_lemi_task.ps1

$ScriptPath = "C:\lemi_monitor\lemi_monitor.py"   # ← adjust if you placed the script elsewhere
$PythonExe  = "pythonw.exe"                         # pythonw = runs without a console window
$TaskName   = "LEMIMonitor"

# Remove old task if it exists
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action   = New-ScheduledTaskAction -Execute $PythonExe -Argument $ScriptPath
$trigger  = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit    (New-TimeSpan -Days 9999) `
    -RestartInterval       (New-TimeSpan -Minutes 2) `
    -RestartCount          999 `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action   $action   `
    -Trigger  $trigger  `
    -Settings $settings `
    -RunLevel Highest   `
    -Force

Write-Host "Task '$TaskName' registered. It will start at next boot."
Write-Host "To start it now:  Start-ScheduledTask -TaskName '$TaskName'"
