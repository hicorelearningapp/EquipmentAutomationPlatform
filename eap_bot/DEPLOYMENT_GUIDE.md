# EAP Bot Deployment Guide

Follow these steps to package and deploy the latest codebase to the live server (`151.185.41.194`).

## Step 1: Package the Code Locally
Run the following from your local Windows PowerShell in the `eap_bot` directory:
```powershell
cd E:\Github\EquipmentAutomationPlatforms\eap_bot
python package_for_deploy.py
```

## Step 2: Upload to the Server
Transfer the newly created zip file to the server using `scp`:
```powershell
scp eap_bot_package.zip root@151.185.41.194:/root/eap_bot/
```

## Step 3: Deploy and Restart
SSH into the server and run the unzipping and restart commands. 

### Option A: From Local PowerShell (One-liner)
You can deploy and restart it remotely in one step:
```powershell
ssh root@151.185.41.194 "cd /root/eap_bot && unzip -o eap_bot_package.zip && bash remote_start.sh"
```

### Option B: From Inside the Server Terminal
If you are already logged into the server via SSH (`root@e2e-130-194:~/eap_bot#`), run:
```bash
unzip -o eap_bot_package.zip
bash remote_start.sh
```

> **Note:** The server uses `nohup` via the `remote_start.sh` script to run the bot, NOT `systemd`. Do not use `systemctl restart eap-bot`.

---

## How to Backup Projects
If you need to backup the live `projects` folder from the server to your local machine:

**1. Create a zip of the projects folder on the server**
Run this via SSH (or inside the server terminal):
```bash
ssh root@151.185.41.194 "cd /root/eap_bot && zip -r projects.zip projects/"
```

**2. Download the backup to your local machine**
Run this from your local Windows PowerShell:
```powershell
scp root@151.185.41.194:/root/eap_bot/projects.zip "E:\Github\EquipmentAutomationPlatforms\eap_bot\projects_backup"
```
