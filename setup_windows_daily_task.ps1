$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$PSScriptRoot\run_daily_scheduler_silent.bat`""
$Trigger = New-ScheduledTaskTrigger -Daily -At 7:00pm
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "CryptoAISystemStep80Daily" -Action $Action -Trigger $Trigger -Settings $Settings -Description "Run Crypto AI System Step80 daily dry run"
