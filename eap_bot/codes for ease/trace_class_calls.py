"""
trace_class_calls.py
====================
Traces which classes call/import/reference which other classes in the
eap_bot source tree.

Usage:
    python "codes for ease/trace_class_calls.py"
    python "codes for ease/trace_class_calls.py" --class ServiceContainer
    python "codes for ease/trace_class_calls.py" --json

Output:
    A table showing:
      File:Class  ->  UsedClass  (via import / attribute / instantiation)
"""

import argparse
import ast
import sys
from collections import defaultdict
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent / "source"


def _find_py_files(root: Path):
    """Yield all .py files under *root*, skipping __pycache__."""
    for p in sorted(root.rglob("*.py")):
        if "__pycache__" in str(p):
            continue
        yield p


def _collect_class_names(root: Path) -> set[str]:
    """Collect all class names defined in the source tree."""
    names = set()
    for py_file in _find_py_files(root):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                names.add(node.name)
    return names


def _trace_file(py_file: Path, known_classes: set[str]) -> dict[str, set[str]]:
    """
    Return a dict: { "ClassName" -> set of used class names } for each class
    defined in *py_file*.

    Also includes a pseudo-entry "<module>" for top-level references.
    """
    try:
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))
    except SyntaxError:
        return {}

    # Build ranges: [(class_name, start_line, end_line)]
    class_ranges: list[tuple[str, int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            end = max(getattr(n, "end_lineno", node.end_lineno or node.lineno)
                      for n in ast.walk(node))
            class_ranges.append((node.name, node.lineno, end))

    def _owning_class(lineno: int) -> str:
        for name, start, end in class_ranges:
            if start <= lineno <= end:
                return name
        return "<module>"

    refs: dict[str, set[str]] = defaultdict(set)

    for node in ast.walk(tree):
        lineno = getattr(node, "lineno", 0)
        owner = _owning_class(lineno)

        # ast.Name — direct name reference (e.g., `StorageService()`)
        if isinstance(node, ast.Name) and node.id in known_classes:
            if node.id != owner:  # don't count self-reference
                refs[owner].add(node.id)

        # ast.Attribute — attribute access on a known class (e.g., `LLMFactory.create_strategy`)
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id in known_classes:
                if node.value.id != owner:
                    refs[owner].add(node.value.id)

        # ImportFrom — e.g., `from source.utils.llm_factory import LLMStrategy`
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                name = alias.asname or alias.name
                if name in known_classes and name != owner:
                    refs[owner].add(name)

    return dict(refs)


def trace(root: Path = SOURCE_ROOT, filter_class: str = None):
    known = _collect_class_names(root)
    all_results: list[tuple[str, str, set[str]]] = []

    for py_file in _find_py_files(root):
        rel = py_file.relative_to(root.parent)
        file_refs = _trace_file(py_file, known)
        for class_name, used in file_refs.items():
            if filter_class and class_name != filter_class and filter_class not in used:
                continue
            all_results.append((str(rel), class_name, used))

    return all_results


def print_table(results):
    if not results:
        print("No class references found.")
        return

    print(f"\n{'File':<50} {'Class/Module':<30} {'Uses'}")
    print("=" * 130)
    for file, cls, used in results:
        used_str = ", ".join(sorted(used))
        print(f"{file:<50} {cls:<30} {used_str}")
    print(f"\n  Total: {len(results)} entries\n")


def print_json(results):
    import json
    out = [
        {"file": f, "class": c, "uses": sorted(u)}
        for f, c, u in results
    ]
    print(json.dumps(out, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Trace class-to-class references in eap_bot")
    parser.add_argument("--class", dest="filter_class", default=None,
                        help="Show only references involving this class name")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    results = trace(filter_class=args.filter_class)
    if args.json:
        print_json(results)
    else:
        print_table(results)


if __name__ == "__main__":
    main()
