import re
import os
from pathlib import Path

# Matches require("file") or require 'file' or require("file.lua")
REQUIRE_PATTERN = re.compile(r'''require\s*\(\s*['"]([^'"]+)['"]\s*\)|require\s+['"]([^'"]+)['"]''')

def _resolve_path(req_path: str, search_dirs: list[Path]) -> Path | None:
    """Finds the absolute path to the required file."""
    # Lifeboat converts . to / for module paths BEFORE adding .lua
    alt_path = req_path.replace(".", "/")
    
    if not req_path.endswith(".lua"):
        req_path += ".lua"
    if not alt_path.endswith(".lua"):
        alt_path += ".lua"
        
    for d in search_dirs:
        # Check direct path
        p = d / req_path
        if p.exists() and p.is_file():
            return p
            
        p2 = d / alt_path
        if p2.exists() and p2.is_file():
            return p2

    return None

def bundle_requires(source: str, root_dir: Path | str | None, loaded_files: dict = None) -> str:
    """
    Recursively scans for require() statements and inlines the file contents.
    Wraps the injected content in an IIFE to preserve scope and return values.
    """
    if loaded_files is None:
        loaded_files = {}
        
    if not root_dir:
        return source
        
    root_dir = Path(root_dir).resolve()
    search_dirs = [root_dir]
    
    if (root_dir / "lib").exists():
        search_dirs.append(root_dir / "lib")
    if (root_dir / "src").exists():
        search_dirs.append(root_dir / "src")

    def replacer(match):
        req_path = match.group(1) or match.group(2)
        
        file_path = _resolve_path(req_path, search_dirs)
        if not file_path:
            return match.group(0)
            
        abs_path = str(file_path.resolve())
        
        if abs_path in loaded_files:
            module_id = loaded_files[abs_path]
            return f"{module_id}"
            
        module_id = f"__LB_MODULE_{len(loaded_files)}"
        loaded_files[abs_path] = module_id
        
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return match.group(0)
            
        content = bundle_requires(content, file_path.parent, loaded_files)
        
        # Create a global cache for the module so subsequent requires return the same value.
        wrapped = f"(function() if not {module_id} then {module_id} = (function()\n{content}\nend)() end return {module_id} end)()"
        return wrapped

    bundled_source = REQUIRE_PATTERN.sub(replacer, source)
    return bundled_source
