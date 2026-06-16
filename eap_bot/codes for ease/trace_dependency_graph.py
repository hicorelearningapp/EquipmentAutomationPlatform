"""
trace_dependency_graph.py
=========================
Builds a full module-level and class-level dependency graph for the eap_bot
source tree, outputting it as either:
  - A text table (default)
  - Mermaid markdown (--mermaid)
  - DOT / Graphviz (--dot)

Usage:
    python "codes for ease/trace_dependency_graph.py"
    python "codes for ease/trace_dependency_graph.py" --mermaid
    python "codes for ease/trace_dependency_graph.py" --dot > deps.dot
    python "codes for ease/trace_dependency_graph.py" --mermaid --output deps.md
"""

import argparse
import ast
import sys
from collections import defaultdict
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent / "source"
PROJECT_PREFIX = "source."


def _find_py_files(root: Path):
    for p in sorted(root.rglob("*.py")):
        if "__pycache__" in str(p):
            continue
        yield p


def _module_name(py_file: Path, root: Path) -> str:
    """Convert a file path to a Python module name relative to the project."""
    rel = py_file.relative_to(root.parent)
    parts = list(rel.with_suffix("").parts)
    return ".".join(parts)


def build_module_graph(root: Path = SOURCE_ROOT) -> dict[str, set[str]]:
    """
    Returns {module_name: set of imported module names} for all source modules.
    Only includes imports within the project (starting with 'source.').
    """
    graph: dict[str, set[str]] = defaultdict(set)

    for py_file in _find_py_files(root):
        mod_name = _module_name(py_file, root)
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(PROJECT_PREFIX) or node.module == "source":
                    graph[mod_name].add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(PROJECT_PREFIX):
                        graph[mod_name].add(alias.name)

    return dict(graph)


def build_class_graph(root: Path = SOURCE_ROOT) -> dict[str, set[str]]:
    """
    Returns {ClassName: set of class names it references}.
    Only tracks classes defined within the source tree.
    """
    # First pass: collect all class names
    all_classes: dict[str, str] = {}  # class_name -> module
    for py_file in _find_py_files(root):
        mod = _module_name(py_file, root)
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                all_classes[node.name] = mod

    known_names = set(all_classes.keys())

    # Second pass: trace references
    graph: dict[str, set[str]] = defaultdict(set)
    for py_file in _find_py_files(root):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        # Build class line ranges
        class_ranges = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                end = max(getattr(n, "end_lineno", node.end_lineno or node.lineno)
                          for n in ast.walk(node))
                class_ranges.append((node.name, node.lineno, end))

        def owning(lineno):
            for name, s, e in class_ranges:
                if s <= lineno <= e:
                    return name
            return None

        for node in ast.walk(tree):
            lineno = getattr(node, "lineno", 0)
            owner = owning(lineno)
            if not owner:
                continue

            if isinstance(node, ast.Name) and node.id in known_names and node.id != owner:
                graph[owner].add(node.id)
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id in known_names and node.value.id != owner:
                    graph[owner].add(node.value.id)
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    n = alias.asname or alias.name
                    if n in known_names and n != owner:
                        graph[owner].add(n)

    return dict(graph)


def _shorten(mod: str) -> str:
    """Shorten module name for display."""
    return mod.replace("source.", "").replace(".", "/")


def print_module_table(graph: dict[str, set[str]]):
    print(f"\n{'Module':<50} {'Depends On'}")
    print("=" * 120)
    for mod in sorted(graph):
        deps = ", ".join(sorted(_shorten(d) for d in graph[mod]))
        print(f"{_shorten(mod):<50} {deps}")
    total_edges = sum(len(v) for v in graph.values())
    print(f"\n  {len(graph)} modules, {total_edges} edges\n")


def print_class_table(graph: dict[str, set[str]]):
    print(f"\n{'Class':<40} {'References'}")
    print("=" * 100)
    for cls in sorted(graph):
        refs = ", ".join(sorted(graph[cls]))
        print(f"{cls:<40} {refs}")
    total_edges = sum(len(v) for v in graph.values())
    print(f"\n  {len(graph)} classes, {total_edges} edges\n")


def print_mermaid(graph: dict[str, set[str]], mode: str = "module"):
    print("```mermaid")
    print("graph LR")
    sanitize = lambda s: s.replace(".", "_").replace("/", "_").replace(" ", "_")
    for src, deps in sorted(graph.items()):
        src_label = _shorten(src) if mode == "module" else src
        src_id = sanitize(src_label)
        for dep in sorted(deps):
            dep_label = _shorten(dep) if mode == "module" else dep
            dep_id = sanitize(dep_label)
            print(f"    {src_id}[\"{src_label}\"] --> {dep_id}[\"{dep_label}\"]")
    print("```")


def print_dot(graph: dict[str, set[str]], mode: str = "module"):
    print("digraph dependencies {")
    print("    rankdir=LR;")
    print('    node [shape=box, style=filled, fillcolor="#e8f4fd"];')
    for src, deps in sorted(graph.items()):
        src_label = _shorten(src) if mode == "module" else src
        for dep in sorted(deps):
            dep_label = _shorten(dep) if mode == "module" else dep
            print(f'    "{src_label}" -> "{dep_label}";')
    print("}")


def main():
    parser = argparse.ArgumentParser(description="Build dependency graph for eap_bot")
    parser.add_argument("--classes", action="store_true", help="Graph class-level instead of module-level")
    parser.add_argument("--mermaid", action="store_true", help="Output Mermaid markdown")
    parser.add_argument("--dot", action="store_true", help="Output DOT/Graphviz format")
    parser.add_argument("--output", "-o", default=None, help="Write output to file instead of stdout")
    args = parser.parse_args()

    if args.classes:
        graph = build_class_graph()
        mode = "class"
    else:
        graph = build_module_graph()
        mode = "module"

    if args.output:
        sys.stdout = open(args.output, "w", encoding="utf-8")

    if args.mermaid:
        print_mermaid(graph, mode)
    elif args.dot:
        print_dot(graph, mode)
    else:
        if mode == "class":
            print_class_table(graph)
        else:
            print_module_table(graph)

    if args.output:
        sys.stdout.close()
        sys.stdout = sys.__stdout__
        print(f"Output written to {args.output}")


if __name__ == "__main__":
    main()
