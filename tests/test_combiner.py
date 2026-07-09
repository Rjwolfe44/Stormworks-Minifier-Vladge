from pathlib import Path
from src.core.passes.combiner import bundle_requires

def test_bundle_requires(tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    
    # Create a library file
    lib_file = lib_dir / "my_math.lua"
    lib_file.write_text("local M = {}; M.add = function(a,b) return a+b end; return M")
    
    # Create main file
    main_source = "local m = require('lib.my_math'); m.add(1, 2)"
    
    print(f"tmp_path: {tmp_path}")
    print(f"lib_file exists? {lib_file.exists()}")
    result = bundle_requires(main_source, tmp_path)
    print(f"result: {result}")
    
    assert "(function()" in result
    assert "M.add = function(a,b) return a+b end" in result
    assert "m.add(1, 2)" in result
    
    # Test deduplication
    main_source_dup = "require('lib.my_math'); require('lib.my_math')"
    result_dup = bundle_requires(main_source_dup, tmp_path)
    # The second require should just return the cached module id
    assert result_dup.count("M.add = function") == 1
