# Registers the autoTiktok posting schedule (Windows Task Scheduler).
# Run AFTER the README warm-up ramp. -Remove unregisters everything.
param([switch]$Remove)

$repo = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python).Source
# keep account names in sync with config.ACCOUNTS
$tasks = @(
    @{ Name = "autoTiktok drama_main 1";  Account = "drama_main";  At = "10:00" },
    @{ Name = "autoTiktok drama_main 2";  Account = "drama_main";  At = "18:30" },
    @{ Name = "autoTiktok horror_main 1"; Account = "horror_main"; At = "12:00" },
    @{ Name = "autoTiktok horror_main 2"; Account = "horror_main"; At = "20:30" }
)

if ($Remove) {
    foreach ($t in $tasks) {
        try { Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false -ErrorAction Stop }
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
    Register-ScheduledTask -TaskName $t.Name -Action $action `
        -Trigger $trigger -Force | Out-Null
    Write-Host "registered $($t.Name) at $($t.At) (+0-40min random)"
}
Write-Host "done -- check with: Get-ScheduledTask -TaskName 'autoTiktok*'"
