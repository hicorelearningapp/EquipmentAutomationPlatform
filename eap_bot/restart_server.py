import os
import signal
import subprocess
import time

def kill_port_8012():
    try:
        output = subprocess.check_output(['netstat', '-tulpn']).decode()
        for line in output.split('\n'):
            if '8012' in line:
                pid = line.strip().split()[-1].split('/')[0]
                print(f"Killing PID {pid}")
                os.kill(int(pid), signal.SIGKILL)
    except Exception as e:
        print(e)

kill_port_8012()
time.sleep(2)
print("Restarting...")
os.system("cd /root/eap_bot && nohup ./venv/bin/python -m uvicorn source.main:app --host 0.0.0.0 --port 8012 > uvicorn_latest.log 2>&1 < /dev/null &")
