param (
    [Parameter(Mandatory=$true)]
    [string]$ServerIP,

    [Parameter(Mandatory=$true)]
    [string]$User,

    [string]$TargetDir = "/home/$User/eap_bot"
)

Write-Host "Restarting on server..." -ForegroundColor Cyan
ssh "${User}@${ServerIP}" "sudo systemctl restart eap-bot"

Write-Host "Restart complete!" -ForegroundColor Green
