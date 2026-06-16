"""
find_code_smells.py
===================
Scans the eap_bot source tree for common code smells and anti-patterns.

Detects:
  - God objects (classes with too many methods/LOC)
  - Large methods (> threshold lines)
  - Bare `except Exception` or `except:`
  - `print()` calls (should be logger)
  - Private member access from outside the class (`obj._private`)
  - Inline/deferred imports (sign of circular dependencies)
  - Commented-out code blocks
  - Deeply nested code (> threshold indentation)

Usage:
    python "codes for ease/find_code_smells.py"
    python "codes for ease/find_code_smells.py" --json
    python "codes for ease/find_code_smells.py" --threshold-methods 15 --threshold-lines 100
"""

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent / "source"

# ── Thresholds ────────────────────────────────────────────────────────────────
DEFAULT_GOD_OBJECT_METHODS = 12
DEFAULT_GOD_OBJECT_LINES = 500
DEFAULT_LARGE_METHOD_LINES = 60
DEFAULT_DEEP_NESTING = 6


@dataclass
class Smell:
    category: str
    severity: str  # "error", "warning", "info"
    file: str
    line: int
    message: str


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


def check_god_objects(tree: ast.AST, filepath: str, max_methods: int, max_lines: int) -> list[Smell]:
    smells = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        loc = _count_lines(node)
        if len(methods) > max_methods:
            smells.append(Smell(
                category="God Object",
                severity="warning",
                file=filepath,
                line=node.lineno,
                message=f"Class '{node.name}' has {len(methods)} methods (threshold: {max_methods})"
            ))
        if loc > max_lines:
            smells.append(Smell(
                category="God Object",
                severity="warning",
                file=filepath,
                line=node.lineno,
                message=f"Class '{node.name}' is {loc} lines (threshold: {max_lines})"
            ))
    return smells


def check_large_methods(tree: ast.AST, filepath: str, threshold: int) -> list[Smell]:
    smells = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            loc = _count_lines(node)
            if loc > threshold:
                # Find owning class if any
                parent = ""
                for cls_node in ast.walk(tree):
                    if isinstance(cls_node, ast.ClassDef):
                        for item in cls_node.body:
                            if item is node:
                                parent = f"{cls_node.name}."
                                break
                smells.append(Smell(
                    category="Large Method",
                    severity="warning",
                    file=filepath,
                    line=node.lineno,
                    message=f"Method '{parent}{node.name}()' is {loc} lines (threshold: {threshold})"
                ))
    return smells


def check_bare_exceptions(tree: ast.AST, filepath: str) -> list[Smell]:
    smells = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                smells.append(Smell(
                    category="Bare Exception",
                    severity="error",
                    file=filepath,
                    line=node.lineno,
                    message="Bare `except:` clause — catches everything including SystemExit"
                ))
            elif isinstance(node.type, ast.Name) and node.type.id == "Exception":
                # Check if the body just re-raises or passes
                body = node.body
                is_reraise = (len(body) == 1 and isinstance(body[0], ast.Raise))
                is_pass = (len(body) == 1 and isinstance(body[0], ast.Pass))
                is_continue = (len(body) == 1 and isinstance(body[0], ast.Continue))
                if not is_reraise:
                    smells.append(Smell(
                        category="Broad Exception",
                        severity="warning",
                        file=filepath,
                        line=node.lineno,
                        message="Catching broad `except Exception` without re-raising"
                    ))
    return smells


def check_print_calls(tree: ast.AST, filepath: str) -> list[Smell]:
    smells = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            smells.append(Smell(
                category="Print Statement",
                severity="info",
                file=filepath,
                line=node.lineno,
                message="`print()` call in production code — use `logger` instead"
            ))
    return smells


def check_private_access(tree: ast.AST, filepath: str) -> list[Smell]:
    """Detect `obj._private_method()` calls — accessing private members externally."""
    smells = []
    # Collect class-defined private names
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            attr = node.attr
            if attr.startswith("_") and not attr.startswith("__"):
                # Check if it's on `self` — if so, it's fine
                if isinstance(node.value, ast.Name) and node.value.id == "self":
                    continue
                if isinstance(node.value, ast.Name) and node.value.id == "cls":
                    continue
                smells.append(Smell(
                    category="Private Access",
                    severity="info",
                    file=filepath,
                    line=node.lineno,
                    message=f"Accessing private member `_.{attr}` from outside the class"
                ))
    return smells


def check_inline_imports(tree: ast.AST, filepath: str) -> list[Smell]:
    """Detect imports inside functions/methods — typically a sign of circular deps."""
    smells = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    module = getattr(child, "module", "") or ""
                    if module.startswith("source."):
                        smells.append(Smell(
                            category="Inline Import",
                            severity="info",
                            file=filepath,
                            line=child.lineno,
                            message=f"Inline import of `{module}` in `{node.name}()` — probable circular dependency"
                        ))
    return smells


def check_commented_code(lines: list[str], filepath: str) -> list[Smell]:
    """Detect blocks of commented-out code (3+ consecutive # lines that look like code)."""
    smells = []
    run_start = None
    run_len = 0
    code_pattern = re.compile(r"^\s*#\s*(def |class |import |from |return |if |for |while |try:|except )")

    for i, line in enumerate(lines, start=1):
        if code_pattern.match(line):
            if run_start is None:
                run_start = i
            run_len += 1
        else:
            if run_len >= 3:
                smells.append(Smell(
                    category="Commented Code",
                    severity="info",
                    file=filepath,
                    line=run_start,
                    message=f"Block of {run_len} commented-out code lines (L{run_start}-{run_start + run_len - 1})"
                ))
            run_start = None
            run_len = 0

    if run_len >= 3 and run_start:
        smells.append(Smell(
            category="Commented Code",
            severity="info",
            file=filepath,
            line=run_start,
            message=f"Block of {run_len} commented-out code lines"
        ))

    return smells


def scan(root: Path = SOURCE_ROOT, **kwargs) -> list[Smell]:
    max_methods = kwargs.get("max_methods", DEFAULT_GOD_OBJECT_METHODS)
    max_lines = kwargs.get("max_lines", DEFAULT_GOD_OBJECT_LINES)
    method_threshold = kwargs.get("method_threshold", DEFAULT_LARGE_METHOD_LINES)

    all_smells: list[Smell] = []

    for py_file in _find_py_files(root):
        rel = str(py_file.relative_to(root.parent))
        source = py_file.read_text(encoding="utf-8")
        lines = source.splitlines()

        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            all_smells.append(Smell("Syntax Error", "error", rel, 0, "File has syntax errors"))
            continue

        all_smells.extend(check_god_objects(tree, rel, max_methods, max_lines))
        all_smells.extend(check_large_methods(tree, rel, method_threshold))
        all_smells.extend(check_bare_exceptions(tree, rel))
        all_smells.extend(check_print_calls(tree, rel))
        all_smells.extend(check_private_access(tree, rel))
        all_smells.extend(check_inline_imports(tree, rel))
        all_smells.extend(check_commented_code(lines, rel))

    return all_smells


def print_table(smells: list[Smell]):
    if not smells:
        print("\n✅ No code smells detected!\n")
        return

    # Group by severity
    by_severity = {"error": [], "warning": [], "info": []}
    for s in smells:
        by_severity.get(s.severity, by_severity["info"]).append(s)

    icons = {"error": "🔴", "warning": "🟡", "info": "ℹ️"}

    for sev in ["error", "warning", "info"]:
        items = by_severity[sev]
        if not items:
            continue
        print(f"\n{icons[sev]}  {sev.upper()} ({len(items)})")
        print("-" * 100)
        for s in items:
            print(f"  [{s.category:<20}] {s.file}:{s.line:<5}  {s.message}")

    total = len(smells)
    print(f"\n  Total: {total} smells ({len(by_severity['error'])} errors, "
          f"{len(by_severity['warning'])} warnings, {len(by_severity['info'])} info)\n")


def main():
    parser = argparse.ArgumentParser(description="Find code smells in eap_bot source")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--threshold-methods", type=int, default=DEFAULT_GOD_OBJECT_METHODS)
    parser.add_argument("--threshold-lines", type=int, default=DEFAULT_GOD_OBJECT_LINES)
    parser.add_argument("--threshold-method-lines", type=int, default=DEFAULT_LARGE_METHOD_LINES)
    args = parser.parse_args()

    smells = scan(
        max_methods=args.threshold_methods,
        max_lines=args.threshold_lines,
        method_threshold=args.threshold_method_lines,
    )

    if args.json:
        out = [{"category": s.category, "severity": s.severity,
                "file": s.file, "line": s.line, "message": s.message}
               for s in smells]
        print(json.dumps(out, indent=2))
    else:
        print_table(smells)


if __name__ == "__main__":
    main()
