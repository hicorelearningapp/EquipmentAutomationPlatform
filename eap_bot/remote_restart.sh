#!/bin/bash
fuser -k 8012/tcp || true
sleep 2
nohup /root/eap_bot/venv/bin/python -m uvicorn source.main:app --host 0.0.0.0 --port 8012 > /root/eap_bot/uvicorn_latest.log 2>&1 < /dev/null &
echo "Restarted"
