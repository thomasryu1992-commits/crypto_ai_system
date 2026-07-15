<#
.SYNOPSIS
  Register (or remove) a Windows Scheduled Task that runs one pipeline cycle on
  an interval, so sustained-paper accumulation survives terminal/session close.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\setup_scheduler_task.ps1
  powershell -ExecutionPolicy Bypass -File scripts\setup_scheduler_task.ps1 -IntervalMinutes 60
  powershell -ExecutionPolicy Bypass -File scripts\setup_scheduler_task.ps1 -Remove

  Verify:  Get-ScheduledTask -TaskName CryptoAISystemPaperScheduler
  Logs:    storage\logs\scheduler.log
  Dashboard: py scripts\dashboard.py
#>
param(
    [int]$IntervalMinutes = 60,
    [switch]$Remove
)

$TaskName = "CryptoAISystemPaperScheduler"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task: $TaskName"
    return
}

$Bat = Join-Path $PSScriptRoot "run_scheduler_once.bat"
if (-not (Test-Path $Bat)) {
    Write-Error "Missing $Bat"
    exit 1
}

$Action  = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$Bat`""
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Settings $Settings -Description "Crypto AI System: one paper pipeline cycle every $IntervalMinutes min" -Force | Out-Null

Write-Host "Registered scheduled task: $TaskName (every $IntervalMinutes min)"
Write-Host "Logs: storage\logs\scheduler.log   Dashboard: py scripts\dashboard.py"
Write-Host "Remove with: powershell -ExecutionPolicy Bypass -File scripts\setup_scheduler_task.ps1 -Remove"
