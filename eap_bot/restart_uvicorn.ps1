param (
    [Parameter(Mandatory=$true)]
    [string]$ServerIP,

    [Parameter(Mandatory=$true)]
    [string]$User,

    [string]$TargetDir = "/root/eap_bot"
)

Write-Host "Restarting on server..." -ForegroundColor Cyan
ssh "${User}@${ServerIP}" "cd $TargetDir && kill -9 637103 && nohup ./venv/bin/python -m uvicorn source.main:app --host 0.0.0.0 --port 8012 > uvicorn_latest.log 2>&1 < /dev/null &"

Write-Host "Restart complete!" -ForegroundColor Green
