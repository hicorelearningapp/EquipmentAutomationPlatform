"""
trace_router_to_service.py
==========================
Maps every API endpoint in the eap_bot project to its full call chain:

    HTTP Method + Path  →  Router.method()  →  service.method()  →  ...

Outputs a table showing what service calls each endpoint makes.

Usage:
    python "codes for ease/trace_router_to_service.py"
    python "codes for ease/trace_router_to_service.py" --json
    python "codes for ease/trace_router_to_service.py" --verbose
"""

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent / "source"
ROUTERS_DIR = SOURCE_ROOT / "routers"


@dataclass
class Endpoint:
    http_method: str
    path: str
    router_class: str
    handler_method: str
    file: str
    line: int
    service_calls: list[str] = field(default_factory=list)
    container_calls: list[str] = field(default_factory=list)


def _find_py_files(root: Path):
    for p in sorted(root.rglob("*.py")):
        if "__pycache__" in str(p):
            continue
        yield p


def _extract_endpoints_from_file(py_file: Path) -> list[Endpoint]:
    """Parse a router file and extract all registered endpoints with their call chains."""
    rel = str(py_file.relative_to(SOURCE_ROOT.parent))
    source = py_file.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(py_file))
    except SyntaxError:
        return []

    endpoints: list[Endpoint] = []
    lines = source.splitlines()

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue

        router_class = node.name

        # Find register_routes method or inline decorators
        method_map: dict[str, ast.FunctionDef] = {}
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_map[item.name] = item

        # Strategy 1: Look for register_routes() that maps self.router.METHOD(path)(self.handler)
        if "register_routes" in method_map:
            reg = method_map["register_routes"]
            for stmt in ast.walk(reg):
                if isinstance(stmt, ast.Call):
                    # Pattern: self.router.post("/path")(self.handler)
                    func = stmt.func
                    if isinstance(func, ast.Call):
                        # This is the self.router.post("/path") part
                        inner_func = func.func
                        if (isinstance(inner_func, ast.Attribute) and
                                isinstance(inner_func.value, ast.Attribute) and
                                isinstance(inner_func.value.value, ast.Name) and
                                inner_func.value.value.id == "self" and
                                inner_func.value.attr == "router"):

                            http_method = inner_func.attr.upper()
                            # Extract path from args
                            path = ""
                            if func.args:
                                first_arg = func.args[0]
                                if isinstance(first_arg, ast.Constant):
                                    path = str(first_arg.value)

                            # Extract handler name from args of outer call
                            handler_name = ""
                            if stmt.args:
                                handler_arg = stmt.args[0]
                                if isinstance(handler_arg, ast.Attribute) and handler_arg.attr:
                                    handler_name = handler_arg.attr

                            if handler_name and handler_name in method_map:
                                handler = method_map[handler_name]
                                svc_calls, ctr_calls = _extract_service_calls(handler)
                                endpoints.append(Endpoint(
                                    http_method=http_method,
                                    path=path,
                                    router_class=router_class,
                                    handler_method=handler_name,
                                    file=rel,
                                    line=handler.lineno,
                                    service_calls=svc_calls,
                                    container_calls=ctr_calls,
                                ))

        # Strategy 2: Look for @self.router.get(...) decorators directly on methods
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in item.decorator_list:
                    if isinstance(dec, ast.Call):
                        dec_func = dec.func
                        if (isinstance(dec_func, ast.Attribute) and
                                isinstance(dec_func.value, ast.Attribute) and
                                dec_func.value.attr == "router"):
                            http_method = dec_func.attr.upper()
                            path = ""
                            if dec.args:
                                first = dec.args[0]
                                if isinstance(first, ast.Constant):
                                    path = str(first.value)
                            svc_calls, ctr_calls = _extract_service_calls(item)
                            endpoints.append(Endpoint(
                                http_method=http_method,
                                path=path,
                                router_class=router_class,
                                handler_method=item.name,
                                file=rel,
                                line=item.lineno,
                                service_calls=svc_calls,
                                container_calls=ctr_calls,
                            ))

    return endpoints


def _extract_service_calls(func_node: ast.AST) -> tuple[list[str], list[str]]:
    """Extract service/storage method calls and container accesses from a function."""
    service_calls: list[str] = []
    container_calls: list[str] = []

    for node in ast.walk(func_node):
        if isinstance(node, ast.Attribute):
            # self.storage.method() or container.service.method()
            if isinstance(node.value, ast.Attribute):
                obj_attr = node.value.attr
                method = node.attr
                # Check if it's self.storage.X()
                if isinstance(node.value.value, ast.Name):
                    obj_name = node.value.value.id
                    if obj_name == "self" and obj_attr == "storage":
                        service_calls.append(f"storage.{method}")
                    elif obj_name == "container":
                        container_calls.append(f"container.{obj_attr}.{method}")
                # container.project_service.storage.X
                elif isinstance(node.value.value, ast.Attribute):
                    if isinstance(node.value.value.value, ast.Name):
                        root_name = node.value.value.value.id
                        mid = node.value.value.attr
                        leaf = node.value.attr
                        if root_name == "container":
                            container_calls.append(f"container.{mid}.{leaf}.{method}")

            # Direct container.X access
            elif isinstance(node.value, ast.Name):
                if node.value.id == "container":
                    container_calls.append(f"container.{node.attr}")

    return service_calls, container_calls


def scan_all_routers() -> list[Endpoint]:
    all_endpoints: list[Endpoint] = []
    for py_file in _find_py_files(ROUTERS_DIR):
        all_endpoints.extend(_extract_endpoints_from_file(py_file))
    return all_endpoints


def print_table(endpoints: list[Endpoint], verbose: bool = False):
    if not endpoints:
        print("\nNo endpoints found.\n")
        return

    print(f"\n{'Method':<8} {'Path':<45} {'Router.Handler':<40} {'Service Calls'}")
    print("=" * 160)

    for ep in sorted(endpoints, key=lambda e: e.path):
        handler = f"{ep.router_class}.{ep.handler_method}"
        calls = []
        if ep.service_calls:
            calls.extend(ep.service_calls[:3])  # show top 3
        if ep.container_calls:
            calls.extend(ep.container_calls[:3])

        calls_str = " | ".join(calls) if calls else "(direct logic in route)"
        print(f"{ep.http_method:<8} {ep.path:<45} {handler:<40} {calls_str}")

        if verbose and (ep.service_calls or ep.container_calls):
            for sc in ep.service_calls:
                print(f"{'':>95}  → {sc}")
            for cc in ep.container_calls:
                print(f"{'':>95}  → {cc}")

    print(f"\n  Total: {len(endpoints)} endpoints\n")


def print_json(endpoints: list[Endpoint]):
    out = [
        {
            "method": ep.http_method,
            "path": ep.path,
            "router_class": ep.router_class,
            "handler": ep.handler_method,
            "file": ep.file,
            "line": ep.line,
            "service_calls": ep.service_calls,
            "container_calls": ep.container_calls,
        }
        for ep in endpoints
    ]
    print(json.dumps(out, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Trace API endpoints to service calls")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show full service call chains")
    args = parser.parse_args()

    endpoints = scan_all_routers()

    if args.json:
        print_json(endpoints)
    else:
        print_table(endpoints, verbose=args.verbose)


if __name__ == "__main__":
    main()
