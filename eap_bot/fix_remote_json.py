import subprocess
import sys

def run_remote():
    cmd = [
        "ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no", "root@151.185.41.194",
        "sed -i 's/Interface Control Document (ICD)/Equipment Data/g' /root/eap_bot/projects/1/ProjectsMetadata/project.json"
    ]
    print("Running command...")
    result = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    print("Return Code:", result.returncode)

if __name__ == "__main__":
    run_remote()
