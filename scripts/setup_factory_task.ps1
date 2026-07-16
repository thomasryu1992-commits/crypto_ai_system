<#
.SYNOPSIS
  Register (or remove) a Windows Scheduled Task that runs one strategy-factory
  generation on an interval, so the paper pool is continuously replenished with
  fresh, independently-validated strategies (directive S11 / section 15).

  The factory only ADDS to the paper pool; it never promotes to testnet/live and
  never bypasses PreOrderRiskGate. Runs less often than the pipeline scheduler —
  the directive prescribes weekly-to-daily generation batches, so this defaults
  to once a day.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\setup_factory_task.ps1
  powershell -ExecutionPolicy Bypass -File scripts\setup_factory_task.ps1 -IntervalMinutes 1440
  powershell -ExecutionPolicy Bypass -File scripts\setup_factory_task.ps1 -Remove

  Verify:  Get-ScheduledTask -TaskName CryptoAISystemStrategyFactory
  Logs:    storage\logs\strategy_factory.log
  Pool:    py run_strategy_factory.py --status
#>
param(
    [int]$IntervalMinutes = 1440,
    [switch]$Remove
)

$TaskName = "CryptoAISystemStrategyFactory"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task: $TaskName"
    return
}

$Bat = Join-Path $PSScriptRoot "run_factory_once.bat"
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
    -Settings $Settings -Description "Crypto AI System: one strategy-factory generation every $IntervalMinutes min (paper pool only)" -Force | Out-Null

Write-Host "Registered scheduled task: $TaskName (every $IntervalMinutes min)"
Write-Host "Logs: storage\logs\strategy_factory.log   Pool: py run_strategy_factory.py --status"
Write-Host "Remove with: powershell -ExecutionPolicy Bypass -File scripts\setup_factory_task.ps1 -Remove"
