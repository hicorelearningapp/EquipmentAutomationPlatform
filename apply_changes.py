"""
apply_changes.py
================
Reads a structured changes file and writes each file block to the correct
location inside CODEBASE_ROOT.

USAGE
-----
1. Set CODEBASE_ROOT below to the absolute path of your eap_bot folder.
   Use forward slashes even on Windows, e.g.:
       CODEBASE_ROOT = "E:/Github/EquipmentAutomationPlatforms/eap_bot"

2. Set CHANGES_FILE to the path of the changes .txt file.
   Can be relative to this script or absolute.

3. Run (preview only, no files written):
       python apply_changes.py

   Run to actually write files:
       python apply_changes.py --apply

FORMAT EXPECTED IN THE CHANGES FILE
-------------------------------------
===FILE: relative/path/from/eap_bot===
<full file content>
===END===

Lines outside FILE blocks are treated as comments and ignored.
"""

import argparse
import os
import sys
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURE THESE TWO PATHS BEFORE RUNNING
# ──────────────────────────────────────────────────────────────────────────────
CODEBASE_ROOT = "E:/Github/EquipmentAutomationPlatforms/eap_bot"
CHANGES_FILE  = "eap_refactor_changes.txt"  # relative to this script, or absolute
# ──────────────────────────────────────────────────────────────────────────────


FILE_START_PREFIX = "===FILE:"
FILE_START_SUFFIX = "==="
FILE_END_MARKER   = "===END==="


def parse_changes(changes_path: Path) -> list:
    """
    Parse the changes file into a list of (relative_path, content) tuples.
    """
    blocks = []
    current_rel_path = None
    current_lines = []

    with open(changes_path, encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.rstrip("\n")

            # Detect block start: ===FILE: some/path===
            if line.startswith(FILE_START_PREFIX) and line.endswith(FILE_START_SUFFIX):
                inner = line[len(FILE_START_PREFIX): -len(FILE_START_SUFFIX)].strip()
                current_rel_path = inner
                current_lines = []
                continue

            # Detect block end
            if line.strip() == FILE_END_MARKER:
                if current_rel_path is not None:
                    blocks.append((current_rel_path, "\n".join(current_lines)))
                current_rel_path = None
                current_lines = []
                continue

            # Inside a block: accumulate lines
            if current_rel_path is not None:
                current_lines.append(line)
                continue

            # Outside any block: ignore (comments / header text)

    if current_rel_path is not None:
        print("WARNING: Reached end of file while inside block for '{}'.".format(current_rel_path))
        print("         That block was NOT included. Check for a missing ===END===.")

    return blocks


def apply_changes(codebase_root: Path, blocks: list, dry_run: bool = True) -> None:
    """
    Write each (relative_path, content) block to codebase_root/relative_path.
    In dry_run mode, only print what would happen without writing anything.
    """
    if not codebase_root.exists():
        print("ERROR: CODEBASE_ROOT does not exist: {}".format(codebase_root))
        sys.exit(1)

    mode_label = "DRY RUN" if dry_run else "APPLYING"
    print("\n{} — CODEBASE_ROOT: {}".format(mode_label, codebase_root))
    print("Total file blocks found: {}\n".format(len(blocks)))

    written = 0
    skipped = 0

    for rel_path_str, content in blocks:
        # Normalise path separators to OS default
        rel_path = Path(rel_path_str.replace("/", os.sep).replace("\\", os.sep))
        target = (codebase_root / rel_path).resolve()

        # Safety check: make sure resolved path stays inside codebase root
        try:
            target.relative_to(codebase_root.resolve())
        except ValueError:
            print("  SKIPPED (path escape attempt): {}".format(rel_path_str))
            skipped += 1
            continue

        exists_before = target.exists()

        if dry_run:
            action = "CREATE" if not exists_before else "OVERWRITE"
            print("  [{}] {}".format(action, target))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            action = "CREATED" if not exists_before else "UPDATED"
            print("  [{}] {}".format(action, target))

        written += 1

    verb = "Would write" if dry_run else "Wrote"
    print("\n{}: {} file(s)  |  Skipped: {}".format(verb, written, skipped))

    if dry_run:
        print("\nTo apply for real, run:  python apply_changes.py --apply\n")
    else:
        print("\nDone. Restart your FastAPI server to pick up the changes.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply EAP codebase refactor changes.")
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Actually write files (default is dry-run / preview only)",
    )
    parser.add_argument(
        "--changes-file",
        default=None,
        help="Path to the changes file (overrides CHANGES_FILE constant)",
    )
    parser.add_argument(
        "--codebase-root",
        default=None,
        help="Path to the eap_bot codebase root (overrides CODEBASE_ROOT constant)",
    )
    args = parser.parse_args()

    changes_file_path = Path(args.changes_file) if args.changes_file else Path(CHANGES_FILE)
    codebase_root_path = Path(args.codebase_root) if args.codebase_root else Path(CODEBASE_ROOT)

    # If changes file is relative, resolve relative to this script's directory
    if not changes_file_path.is_absolute():
        changes_file_path = (Path(__file__).parent / changes_file_path).resolve()

    if not changes_file_path.exists():
        print("ERROR: Changes file not found: {}".format(changes_file_path))
        sys.exit(1)

    print("Reading changes from: {}".format(changes_file_path))
    blocks = parse_changes(changes_file_path)

    if not blocks:
        print("No file blocks found in the changes file. Check the format.")
        sys.exit(1)

    apply_changes(
        codebase_root=codebase_root_path.resolve(),
        blocks=blocks,
        dry_run=not args.apply,
    )


if __name__ == "__main__":
    main()
