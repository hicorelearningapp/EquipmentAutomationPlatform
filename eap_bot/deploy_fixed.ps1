param (
    [Parameter(Mandatory=$true)]
    [string]$ServerIP,

    [Parameter(Mandatory=$true)]
    [string]$User,

    [string]$TargetDir = "/home/$User/eap_bot"
)

$ZipFile = "eap_bot_package.zip"

Write-Host "Packaging codebase with python script..." -ForegroundColor Cyan
python package_for_deploy.py

Write-Host "Transferring to $ServerIP..." -ForegroundColor Cyan
scp $ZipFile "${User}@${ServerIP}:${TargetDir}/"

Write-Host "Deploying on server..." -ForegroundColor Cyan
ssh "${User}@${ServerIP}" "cd $TargetDir && unzip -o $ZipFile && ./venv/bin/pip install -r requirements.txt && sudo systemctl restart eap-bot"

Write-Host "Deployment complete!" -ForegroundColor Green
Remove-Item $ZipFile
