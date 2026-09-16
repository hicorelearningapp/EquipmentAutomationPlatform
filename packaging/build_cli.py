"""Assemble the folder that ships eap_cli.py as a program, with Python inside it.

    eap_bot\\.venv\\Scripts\\python.exe packaging\\build_cli.py --data <data folder> --zip

Produces dist/eap_cli:

    runtime\\eap_cli.exe         Python, renamed, with the libraries the backend needs
    eap_bot\\eap_cli.py          the one file: every endpoint, no web server
    eap_bot\\source\\...          the backend code it calls
    eap_bot\\models\\...          the embedding model and the token encoding
    eap_cli.cmd                 run one request without typing the long path
    demo.cmd, demo.py           a short tour of the stays-open mode
    data\\projects\\             projects to open straight away (only with --data)
    README.txt                  how to start it, and how C# starts it

Nothing here is secret: no API key and no .env file. Whoever runs it passes the key as an
environment variable.
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_DIR / "eap_bot"
DIST_DIR = PROJECT_DIR / "dist" / "eap_cli"
EXE_NAME = "eap_cli.exe"

# Left out of the shipped copy: tests, samples, anything written while running, the
# development settings file that holds an API key, and the development environment.
BACKEND_EXCLUDES = shutil.ignore_patterns(
    "test", "demo_docs", "files for test", "codes for ease", "projects_backup", ".env",
    ".venv", "logs", "runtime_storage", "projects", "vectorstores", "__pycache__", "*.pyc",
    "*.zip", "*.tar.gz", "error.txt", "extractor_error.txt", "package-lock.json",
)

README = """HiCore EAP - the backend as a command-line program
=================================================

Every endpoint of the equipment automation backend, with no web server and no network port.
Python and all the libraries are inside this folder; nothing needs installing.

Two ways to run it. Both run the same code in the same file.

1. One request per run - the simplest, like any command-line tool:

    eap_cli.cmd GET /GetAllProjects
    eap_cli.cmd GET /LoadProject/3
    eap_cli.cmd POST /CreateProject @sample\\create_project.json

   or without the wrapper, which is what another program would call:

    runtime\\{exe} -E eap_bot\\eap_cli.py GET /LoadProject/3

   It prints {{"status": 200, "body": {{...}}}} and sets an exit code: 0 worked, 1 the
   backend answered with an error, 2 the command itself was wrong.

   Starting up takes a few seconds, and this way pays it every time.

2. Stays open - what an application should use:

    runtime\\{exe} -E eap_bot\\eap_cli.py --serve

   It reports {{"type": "ready", "version": "1.0"}} when it can take requests, then reads one
   JSON request per line and writes one answer per line:

    in :  {{"id": "42", "method": "GET", "path": "/LoadProject/12"}}
    out:  {{"id": "42", "status": 200, "body": {{...}}}}

   Startup is paid once and each request is answered in hundredths of a second. Answers can
   come back in a different order, so match them by id. Closing the input stops it.

   demo.py in this folder is a working example of that conversation.

The -E matters: it tells the runtime to ignore PYTHON* environment variables. Some machines
have PYTHONHOME or PYTHONPATH set for another Python installation, and without -E the program
would try to use that one and fail to start.

Settings are passed as environment variables:

    EAP_DATA_DIR      where projects, MES templates and logs are kept
                      (default: %LOCALAPPDATA%\\HiCore\\BraceLink)
    EAP_STORAGE_ROOT  where projects are kept, if not the default inside the data folder
    LLM_PROVIDER      groq
    LLM_MODEL_NAME    for example openai/gpt-oss-120b
    GROQ_API_KEY      the AI key. It starts without one; only the AI features fail until set.
    EAP_VERBOSE=1     also show the log lines, which otherwise go to the logs folder

This folder contains no API key.
"""


def run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"failed: {' '.join(command)}\n{result.stdout}\n{result.stderr}")


def find_python_to_copy() -> Path:
    """The self-contained Python we ship (a uv-managed CPython, not the system one)."""
    candidates = sorted((Path(os.environ["APPDATA"]) / "uv" / "python").glob("cpython-3.12*-windows-x86_64-none"))
    if not candidates:
        raise SystemExit("no self-contained Python 3.12 found; run: uv python install 3.12")
    return candidates[-1]


def folder_size_mb(path: Path) -> float:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-existing", action="store_true", help="do not delete dist first")
    parser.add_argument("--zip", action="store_true",
                        help="also pack the folder into dist/eap_cli_<date>.zip to send on")
    parser.add_argument("--data", type=Path, default=None,
                        help="a data folder to include as data\\, so it opens with real projects")
    args = parser.parse_args()

    started = time.perf_counter()
    if DIST_DIR.exists() and not args.keep_existing:
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # 1. The Python runtime
    source_python = find_python_to_copy()
    runtime_dir = DIST_DIR / "runtime"
    print(f"copying the Python runtime from {source_python.name} ...")
    shutil.copytree(source_python, runtime_dir, dirs_exist_ok=True)
    for marker in runtime_dir.rglob("EXTERNALLY-MANAGED"):
        marker.unlink()  # our own copy, so we may install into it

    # 2. The libraries the backend needs
    print("installing the libraries ...")
    run(["uv", "pip", "install", "--system", "--python", str(runtime_dir / "python.exe"),
         "-r", str(BACKEND_DIR / "requirements-local.txt")])

    # 3. Remove parts of Python the backend never uses
    for unused in [runtime_dir / "tcl", runtime_dir / "Lib" / "tkinter", runtime_dir / "include",
                   runtime_dir / "Lib" / "site-packages" / "pip"]:
        if unused.is_dir():
            shutil.rmtree(unused, ignore_errors=True)
    for leftover in runtime_dir.rglob("_tkinter*.pyd"):
        leftover.unlink(missing_ok=True)

    # 4. The program name to start
    shutil.copy2(runtime_dir / "python.exe", runtime_dir / EXE_NAME)

    # 5. The backend itself, eap_cli.py included
    print("copying the backend ...")
    shutil.copytree(BACKEND_DIR, DIST_DIR / "eap_bot", ignore=BACKEND_EXCLUDES, dirs_exist_ok=True)

    if not (DIST_DIR / "eap_bot" / "eap_cli.py").exists():
        raise SystemExit("eap_cli.py is missing from the shipped folder")
    model = DIST_DIR / "eap_bot" / "models" / "onnx" / "all-MiniLM-L6-v2" / "model.onnx"
    if not model.exists():
        raise SystemExit("the embedding model is missing from eap_bot/models")
    if (DIST_DIR / "eap_bot" / ".env").exists():
        raise SystemExit("a .env file ended up in the shipped folder; it must not be included")

    (DIST_DIR / "README.txt").write_text(README.format(exe=EXE_NAME), encoding="utf-8")

    # 6. The files that make it easy to try
    shipped = PROJECT_DIR / "packaging" / "shipped_files"
    for name in ("HOW_TO_TRY_IT.md", "eap_cli.cmd", "demo.cmd", "demo.py"):
        shutil.copy2(shipped / name, DIST_DIR / name)
    sample_dir = DIST_DIR / "sample"
    sample_dir.mkdir(exist_ok=True)
    for name in ("ETCH_Z500_GEM_Spec_Demo.pdf", "create_project.json", "ask_question.json"):
        shutil.copy2(shipped / name, sample_dir / name)

    # 7. Projects to open straight away (a demo package, never an installer)
    if args.data:
        if not (args.data / "projects").is_dir():
            raise SystemExit(f"{args.data} has no projects folder")
        shutil.copytree(args.data, DIST_DIR / "data", dirs_exist_ok=True)
        count = sum(1 for p in (DIST_DIR / "data" / "projects").iterdir() if p.is_dir())
        print(f"included {count} project(s) in data\\")

    print(f"\nbuilt {DIST_DIR}")
    print(f"  runtime : {folder_size_mb(runtime_dir):7.0f} MB")
    print(f"  eap_bot : {folder_size_mb(DIST_DIR / 'eap_bot'):7.0f} MB")
    print(f"  total   : {folder_size_mb(DIST_DIR):7.0f} MB in {time.perf_counter() - started:.0f}s")
    print(f"\ntry it with : eap_cli.cmd GET /GetAllProjects")
    print(f"C# starts it: runtime\\{EXE_NAME} -E eap_bot\\eap_cli.py --serve")

    if args.zip:
        stamp = time.strftime("%Y-%m-%d")
        archive = DIST_DIR.parent / f"eap_cli_{stamp}"
        print(f"\npacking {archive.name}.zip ...")
        packing_started = time.perf_counter()
        shutil.make_archive(str(archive), "zip", root_dir=DIST_DIR.parent, base_dir=DIST_DIR.name)
        zipped = archive.with_suffix(".zip")
        print(f"  {zipped}")
        print(f"  {zipped.stat().st_size / 1e6:.0f} MB in {time.perf_counter() - packing_started:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
