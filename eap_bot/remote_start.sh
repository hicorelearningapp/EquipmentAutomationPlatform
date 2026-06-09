#!/bin/bash
cd /root/eap_bot
fuser -k 8012/tcp || true
sleep 2
nohup ./venv/bin/python -m uvicorn source.main:app --host 0.0.0.0 --port 8012 > uvicorn_latest.log 2>&1 < /dev/null &
echo "Uvicorn started"
