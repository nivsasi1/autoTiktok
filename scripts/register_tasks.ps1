# Registers the autoTiktok posting schedule (Windows Task Scheduler).
# Run AFTER the README warm-up ramp. -Remove unregisters everything.
param([switch]$Remove)

$repo = Split-Path -Parent $PSScriptRoot
$taskPath = "\autoTiktok\"   # group all tasks under one Task Scheduler folder
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "python not found on PATH -- install Python or add it to PATH, then re-run"
    exit 1
}
$python = $pythonCmd.Source
# keep account names in sync with config.ACCOUNTS
$tasks = @(
    @{ Name = "redditregrets 1";  Account = "redditregrets";  At = "10:00" },
    @{ Name = "redditregrets 2";  Account = "redditregrets";  At = "18:30" },
    @{ Name = "nosleeptonight 1"; Account = "nosleeptonight"; At = "12:00" },
    @{ Name = "nosleeptonight 2"; Account = "nosleeptonight"; At = "20:30" }
)

if ($Remove) {
    foreach ($t in $tasks) {
        try { Unregister-ScheduledTask -TaskName $t.Name -TaskPath $taskPath -Confirm:$false -ErrorAction Stop }
        catch {}
    }
    Write-Host "autoTiktok tasks removed"
    exit 0
}

foreach ($t in $tasks) {
    $action = New-ScheduledTaskAction -Execute $python `
        -Argument "main.py --post --account $($t.Account)" `
        -WorkingDirectory $repo
    $trigger = New-ScheduledTaskTrigger -Daily -At $t.At
    $trigger.RandomDelay = "PT40M"   # 0-40 min drift, human-looking
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
    Register-ScheduledTask -TaskName $t.Name -TaskPath $taskPath -Action $action `
        -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Host "registered $($t.Name) at $($t.At) (+0-40min random)"
}
Write-Host "done -- check with: Get-ScheduledTask -TaskPath '\autoTiktok\'"
