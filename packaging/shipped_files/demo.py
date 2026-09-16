"""A short tour of the backend, the way an application uses it.

Run it through demo.cmd, or directly:

    runtime\\eap_cli.exe -E demo.py

It starts eap_cli.py --serve once, waits until it reports ready, sends several requests over
its input, prints each answer and how long it took, then stops it by closing the input.

The client below is about 60 lines. The C# side does the same thing.
"""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = [str(HERE / "runtime" / "eap_cli.exe"), "-E", str(HERE / "eap_bot" / "eap_cli.py"), "--serve"]
SAMPLE_PDF = HERE / "sample" / "ETCH_Z500_GEM_Spec_Demo.pdf"


class Backend:
    """Starts the backend and talks to it: one JSON request per line, one answer per line."""

    def __init__(self):
        self.process = subprocess.Popen(
            BACKEND, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1, cwd=str(HERE),
        )
        self.answers, self.ready, self.next_id = {}, threading.Event(), 0
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=lambda: [None for _ in self.process.stderr], daemon=True).start()
        if not self.ready.wait(120):
            raise SystemExit("the backend did not start")

    def _read(self):
        for line in self.process.stdout:
            if not line.strip():
                continue
            message = json.loads(line)
            if message.get("type") == "ready":
                self.ready.set()
            elif message.get("id") in self.answers:
                self.answers[message["id"]].append(message)

    def ask(self, method, path, body=None, files=None, form=None):
        self.next_id += 1
        request_id = str(self.next_id)
        self.answers[request_id] = []
        request = {"id": request_id, "method": method, "path": path}
        if body is not None:
            request["body"] = body
        if files:
            request["files"] = files
        if form:
            request["form"] = form  # the extra fields an upload needs, such as document_type
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()

        deadline = time.time() + 600
        while not self.answers[request_id] and time.time() < deadline:
            time.sleep(0.01)
        return self.answers.pop(request_id)[0]

    def stop(self):
        self.process.stdin.close()
        return self.process.wait(timeout=30)


def show(backend, label, method, path, body=None, files=None, form=None):
    started = time.perf_counter()
    answer = backend.ask(method, path, body, files, form)
    seconds = time.perf_counter() - started
    content = answer.get("body", answer.get("text"))
    print(f"  {label:<28} {answer['status']}  {seconds:5.2f}s  {str(content)[:70]}")
    return answer


def main() -> int:
    print(f"data folder: {os.environ.get('EAP_DATA_DIR', '(default)')}")
    started = time.perf_counter()
    backend = Backend()
    print(f"backend ready in {time.perf_counter() - started:.1f}s\n")

    show(backend, "is it alive", "GET", "/health")
    show(backend, "system summary", "GET", "/GetSystemSummary")
    show(backend, "list all projects", "GET", "/GetAllProjects")
    show(backend, "open Hicore", "GET", "/LoadProject/3")
    created = show(backend, "create a project", "POST", "/CreateProject",
                   {"ProjectName": f"Demo {int(time.time())}", "VendorName": "HiCore",
                    "ProjectCode": "DEMO-1"})
    project_id = created["body"]["ProjectID"]

    if SAMPLE_PDF.exists():
        show(backend, "upload a manual (PDF)", "POST", f"/UploadDocument/{project_id}",
             files=[{"field": "file", "path": str(SAMPLE_PDF)}],
             form={"document_type": "GEM Manual"})
    show(backend, "open the new project", "GET", f"/LoadProject/{project_id}")
    show(backend, "a project that is missing", "GET", "/LoadProject/99999")
    show(backend, "delete the project", "DELETE", f"/DeleteProject/{project_id}")

    print("\nNotice the first line: starting up costs a few seconds, and every request after")
    print("that is answered in hundredths of a second. That is why an application starts it")
    print("once and keeps it open, instead of starting it for every click.")
    print("\nThe AI features (analyze, ask a question, auto-map) need a Groq API key.")
    print("Set GROQ_API_KEY in demo.cmd or in your environment and they will work too.")
    print(f"\nstopping the backend ... exit code {backend.stop()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
