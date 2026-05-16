# EAP Bot Deployment Script for Azure VM
# Usage: ./deploy.ps1 -ServerIP "1.2.3.4" -User "azureuser"

param (
    [Parameter(Mandatory=$true)]
    [string]$ServerIP,

    [Parameter(Mandatory=$true)]
    [string]$User,

    [string]$TargetDir = "/home/$User/eap_bot"
)

$ZipFile = "eap_bot_package.zip"

Write-Host "Packaging codebase..." -ForegroundColor Cyan
# Exclude runtime data and venv
Compress-Archive -Path "app", "requirements.txt", ".env.server" -DestinationPath $ZipFile -Force

Write-Host "Transferring to $ServerIP..." -ForegroundColor Cyan
scp $ZipFile "${User}@${ServerIP}:${TargetDir}/"

Write-Host "Deploying on server..." -ForegroundColor Cyan
# This assumes the user has set up the directory and venv on the server
ssh "${User}@${ServerIP}" "cd $TargetDir && unzip -o $ZipFile && mv .env.server .env && ./venv/bin/pip install -r requirements.txt && sudo systemctl restart eap-bot"

Write-Host "Deployment complete!" -ForegroundColor Green
Remove-Item $ZipFile
