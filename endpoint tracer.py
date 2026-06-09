import os
import ast
from pathlib import Path
from typing import Set, Dict, List, Optional

class FastAPITargetedTracer:
    def __init__(self, codebase_path: str):
        # Crucial: This must be the root directory that contains the 'source' folder.
        self.codebase_path = Path(codebase_path).resolve()

    def _get_file_imports(self, file_path: Path) -> Dict[str, str]:
        """Maps imported names (e.g., 'EquipmentSpec') to their module origin (e.g., 'source.schemas.secsgem')."""
        import_map = {}
        if not file_path.exists() or file_path.suffix != '.py':
            return import_map

        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                tree = ast.parse(f.read(), filename=str(file_path))
            except SyntaxError:
                return import_map

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    import_map[alias.name] = alias.name
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for alias in node.names:
                        import_map[alias.name] = node.module
        return import_map

    def _get_names_used_in_context(self, file_path: Path, func_name: str) -> Set[str]:
        """
        Finds used variables/classes. If the function is inside a class, 
        it ALSO scans the __init__ method to catch class-level dependency injections.
        """
        used_names = set()
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                tree = ast.parse(f.read(), filename=str(file_path))
            except SyntaxError:
                return used_names

        # 1. First, check if this is a Class-based setup
        for class_node in ast.walk(tree):
            if isinstance(class_node, ast.ClassDef):
                methods = [n for n in class_node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                method_names = [m.name for m in methods]
                
                # If our target function lives in this class
                if func_name in method_names:
                    for method in methods:
                        # Scan both the target function AND the init constructor
                        if method.name in ('__init__', func_name):
                            for child in ast.walk(method):
                                if isinstance(child, ast.Name):
                                    used_names.add(child.id)
                    return used_names

        # 2. Fallback: If it's just a standard top-level function router
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
                for child in ast.walk(node):
                    if isinstance(child, ast.Name):
                        used_names.add(child.id)
                break
                
        return used_names

    def _resolve_module_to_path(self, module_name: str) -> Optional[Path]:
        """Resolves a Python module path (source.services...) to a physical file."""
        parts = module_name.split('.')
        
        # Strategy 1: It's a direct file (e.g., source/services/storage_service.py)
        file_path = self.codebase_path.joinpath(*parts).with_suffix('.py')
        if file_path.is_file():
            return file_path

        # Strategy 2: It's a package directory (e.g., source/services/__init__.py)
        dir_path = self.codebase_path.joinpath(*parts, '__init__.py')
        if dir_path.is_file():
            return dir_path
            
        return None

    def trace_endpoint(self, entry_file: str, endpoint_func_name: str) -> Dict[str, List]:
        entry_path = self.codebase_path / entry_file
        if not entry_path.exists():
            raise FileNotFoundError(f"Entry file not found: {entry_path}")

        # Analyze file context (now class-aware)
        used_names = self._get_names_used_in_context(entry_path, endpoint_func_name)
        file_imports = self._get_file_imports(entry_path)

        visited_files = {entry_path}
        to_visit = set()

        for name in used_names:
            if name in file_imports:
                module_source = file_imports[name]
                resolved_path = self._resolve_module_to_path(module_source)
                if resolved_path and resolved_path not in visited_files:
                    to_visit.add(resolved_path)
                elif not resolved_path:
                    print(
                        f"[WARNING] I know '{name}' is needed, but I cannot find the file "
                        f"for '{module_source}' in your codebase path ({self.codebase_path})."
                    )

        while to_visit:
            current_file = to_visit.pop()
            if current_file in visited_files:
                continue

            visited_files.add(current_file)

            downstream_imports = self._get_file_imports(current_file)
            for mod_name in downstream_imports.values():
                resolved = self._resolve_module_to_path(mod_name)
                if resolved and resolved not in visited_files:
                    to_visit.add(resolved)
                elif not resolved:
                    print(
                        f"[WARNING] Downstream dependency missing: could not find file "
                        f"for '{mod_name}' in your codebase path ({self.codebase_path})."
                    )

        return {
            "entry_point": str(entry_path),
            "target_endpoint": endpoint_func_name,
            "total_files_traced": len(visited_files),
            "file_paths": [str(p) for p in visited_files],
            "filenames": [p.name for p in visited_files]
        }


class DependencyTextCompiler:
    def __init__(self, file_paths: List[str], codebase_path: str, output_dir: str):
        self.file_paths = [Path(p) for p in file_paths]
        self.codebase_path = Path(codebase_path).resolve()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def compile_to_text(self, txt_filename: str = "compiled_endpoint_code.txt") -> str:
        output_path = self.output_dir / txt_filename
        
        if not self.file_paths:
            raise ValueError("No files provided to compile.")

        with open(output_path, 'w', encoding='utf-8') as out_file:
            for file_path in self.file_paths:
                if file_path.exists() and file_path.is_file():
                    try:
                        display_path = file_path.relative_to(self.codebase_path)
                    except ValueError:
                        display_path = file_path
                    
                    out_file.write(f"{'=' * 80}\n")
                    out_file.write(f"--- FILE PATH: {display_path} ---\n")
                    out_file.write(f"{'=' * 80}\n\n")
                    
                    with open(file_path, 'r', encoding='utf-8') as in_file:
                        out_file.write(in_file.read())
                    
                    out_file.write("\n\n\n")

        return str(output_path)


# === Usage Example ===
if __name__ == "__main__":
    # FIX: Use the ABSOLUTE path to the root folder of your project
    # (The folder that contains the 'source' folder inside it)
    codebase_directory = r"E:\Github\EquipmentAutomationPlatforms\eap_bot"

    tracer = FastAPITargetedTracer(codebase_path=codebase_directory)

    try:
        trace_results = tracer.trace_endpoint(
            entry_file="source/routers/equipment_routes.py",
            endpoint_func_name="generate_reports",
        )

        print(
            f"\nTraced {trace_results['total_files_traced']} files "
            f"for endpoint '{trace_results['target_endpoint']}':"
        )
        for fname in trace_results['filenames']:
            print(f" - {fname}")

        compiler = DependencyTextCompiler(
            file_paths=trace_results['file_paths'],
            codebase_path=codebase_directory,
            output_dir=r"E:\Github\EquipmentAutomationPlatforms\exports",
        )

        txt_location = compiler.compile_to_text("equipment_endpoint_code.txt")
        print(f"\nCompiled successfully into single text file at: {txt_location}")

    except FileNotFoundError as e:
        print(f"Error: {e}")