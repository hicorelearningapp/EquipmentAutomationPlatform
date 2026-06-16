"""
find_duplicated_methods.py
==========================
Finds methods with the same name defined in different files/classes
across the eap_bot source tree. This helps identify DRY violations
where the same logic may be copy-pasted.

Usage:
    python "codes for ease/find_duplicated_methods.py"
    python "codes for ease/find_duplicated_methods.py" --min-lines 10
    python "codes for ease/find_duplicated_methods.py" --json
"""

import argparse
import ast
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent / "source"


@dataclass
class MethodInfo:
    name: str
    class_name: str  # "" if module-level
    file: str
    line: int
    lines: int
    signature: str


def _find_py_files(root: Path):
    for p in sorted(root.rglob("*.py")):
        if "__pycache__" in str(p):
            continue
        yield p


def _count_lines(node: ast.AST) -> int:
    end = getattr(node, "end_lineno", None)
    start = getattr(node, "lineno", None)
    if end and start:
        return end - start + 1
    return 0


def _get_signature(node: ast.FunctionDef) -> str:
    """Extract function signature as string."""
    args = []
    for arg in node.args.args:
        args.append(arg.arg)
    return f"({', '.join(args)})"


def collect_methods(root: Path = SOURCE_ROOT, min_lines: int = 5) -> dict[str, list[MethodInfo]]:
    """Returns { method_name: [MethodInfo, ...] } for methods appearing in 2+ places."""
    all_methods: dict[str, list[MethodInfo]] = defaultdict(list)

    for py_file in _find_py_files(root):
        rel = str(py_file.relative_to(root.parent))
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        loc = _count_lines(item)
                        if loc >= min_lines:
                            all_methods[item.name].append(MethodInfo(
                                name=item.name,
                                class_name=node.name,
                                file=rel,
                                line=item.lineno,
                                lines=loc,
                                signature=_get_signature(item),
                            ))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Module-level function (check it's not nested in a class)
                is_class_method = False
                for cls in ast.walk(tree):
                    if isinstance(cls, ast.ClassDef):
                        for item in cls.body:
                            if item is node:
                                is_class_method = True
                                break
                if not is_class_method:
                    loc = _count_lines(node)
                    if loc >= min_lines:
                        all_methods[node.name].append(MethodInfo(
                            name=node.name,
                            class_name="",
                            file=rel,
                            line=node.lineno,
                            lines=loc,
                            signature=_get_signature(node),
                        ))

    # Filter to only duplicates (2+ locations across different files)
    duplicates = {}
    for name, infos in all_methods.items():
        if name.startswith("__") and name.endswith("__"):
            continue  # skip dunder methods
        files = set(i.file for i in infos)
        if len(files) >= 2:
            duplicates[name] = infos

    return duplicates


def print_table(duplicates: dict[str, list[MethodInfo]]):
    if not duplicates:
        print("\n✅ No duplicated methods found!\n")
        return

    print(f"\n{'Method Name':<35} {'Class':<30} {'File':<50} {'Line':<6} {'LOC'}")
    print("=" * 145)

    for name in sorted(duplicates):
        infos = duplicates[name]
        first = True
        for info in sorted(infos, key=lambda i: i.file):
            label = name if first else ""
            cls = info.class_name or "(module)"
            print(f"{label:<35} {cls:<30} {info.file:<50} {info.line:<6} {info.lines}")
            first = False
        print()

    total = sum(len(v) for v in duplicates.values())
    print(f"  {len(duplicates)} duplicated method names across {total} locations\n")


def print_json(duplicates: dict[str, list[MethodInfo]]):
    out = {}
    for name, infos in sorted(duplicates.items()):
        out[name] = [
            {"class": i.class_name, "file": i.file, "line": i.line,
             "lines": i.lines, "signature": i.signature}
            for i in infos
        ]
    print(json.dumps(out, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Find duplicated methods across eap_bot source")
    parser.add_argument("--min-lines", type=int, default=5,
                        help="Minimum method length (LOC) to consider")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    duplicates = collect_methods(min_lines=args.min_lines)

    if args.json:
        print_json(duplicates)
    else:
        print_table(duplicates)


if __name__ == "__main__":
    main()
