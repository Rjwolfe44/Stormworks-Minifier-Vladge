"""
VladgeMinifier - SW Bundler
Pre-processes Lua code to stitch multiple files together using require().
"""

import re
from pathlib import Path

def bundle_code(source_code: str, base_dir: Path) -> str:
    """
    Scans the source code for require("filename.lua") and replaces it with
    an inline self-executing function containing the required file's code.
    This safely scopes the required file's locals and returns its exports.
    """
    # Regex to match require("path") or require "path"
    require_pattern = re.compile(r'require\s*\(?\s*(["\'])([^"\']+)\1\s*\)?')
    
    bundled_files = set()
    
    def require_replacer(match):
        path_str = match.group(2)
        
        # Resolve path relative to the current file's directory
        target_path = (base_dir / path_str).resolve()
        
        if not target_path.exists():
            # If they don't provide .lua extension, try adding it
            if not target_path.suffix:
                target_path = target_path.with_suffix('.lua')
                
        if not target_path.exists():
            print(f"Warning: SW Bundler could not find required file '{path_str}' at '{target_path}'. Leaving require() intact.")
            return match.group(0)
            
        if target_path in bundled_files:
            # Prevent infinite recursion if files require each other
            print(f"Warning: Circular dependency or duplicate require detected for '{target_path.name}'.")
            return "nil --[[circular require]]"
            
        bundled_files.add(target_path)
        
        try:
            req_code = target_path.read_text(encoding="utf-8")
            
            # Recursively bundle the required file as well!
            req_code = bundle_code(req_code, target_path.parent)
            
            # Wrap in a self-executing anonymous function
            return f"(function()\n{req_code}\nend)()"
            
        except Exception as e:
            print(f"Warning: Error reading required file '{target_path.name}': {e}")
            return match.group(0)

    # Perform substitution
    bundled_code = require_pattern.sub(require_replacer, source_code)
    return bundled_code
