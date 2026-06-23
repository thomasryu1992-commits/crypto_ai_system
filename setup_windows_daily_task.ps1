$TaskName = "Crypto AI Daily Operational Dry Run"

$ProjectDir = $PSScriptRoot
$BatPath = Join-Path $ProjectDir "run_daily_operational_dry_run.bat"

# PC 시간이 한국 시간이라면 19:00
# PC 시간이 베트남 시간이라면 한국시간 19:00 = 베트남시간 17:00
$RunTime = "19:00"

if (!(Test-Path $BatPath)) {
    Write-Host "BAT file not found: $BatPath"
    exit 1
}

$Action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$BatPath`"" `
    -WorkingDirectory $ProjectDir

$Trigger = New-ScheduledTaskTrigger `
    -Daily `
    -At $RunTime

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Runs Crypto AI System operational dry run daily." `
    -Force

Write-Host "Scheduled task created:"
Write-Host "Task Name: $TaskName"
Write-Host "Run Time: $RunTime"
Write-Host "Project Dir: $ProjectDir"
Write-Host "BAT Path: $BatPath"