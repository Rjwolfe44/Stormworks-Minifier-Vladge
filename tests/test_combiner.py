"""Combiner / LifeBoat library path resolution tests."""

import json
from pathlib import Path

from src.core.passes.combiner import bundle_requires
from src.core.lifeboat_project import discover_library_paths
from src.core.minifier import minify
from src.core.validate import validate_minified


def test_bundle_requires(tmp_path: Path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    lib_file = lib_dir / "my_math.lua"
    lib_file.write_text("local M = {}; M.add = function(a,b) return a+b end; return M")

    main_source = "local m = require('lib.my_math'); m.add(1, 2)"
    result = bundle_requires(main_source, tmp_path)

    assert "(function()" in result
    assert "M.add = function(a,b) return a+b end" in result
    assert "m.add(1, 2)" in result

    main_source_dup = "require('lib.my_math'); require('lib.my_math')"
    result_dup = bundle_requires(main_source_dup, tmp_path)
    assert result_dup.count("M.add = function") == 1


def test_build_libs_resolution(tmp_path: Path):
    mod = tmp_path / "_build" / "libs" / "LifeBoatAPI" / "Maths"
    mod.mkdir(parents=True)
    (mod / "LBVec.lua").write_text("local V={} return V", encoding="utf-8")

    src = 'local V = require("LifeBoatAPI.Maths.LBVec")'
    out = bundle_requires(src, tmp_path)
    assert "require" not in out
    assert "local V={}" in out


def test_vscode_library_paths(tmp_path: Path):
    external = tmp_path / "external_libs"
    nest = external / "Shared" / "Util"
    nest.mkdir(parents=True)
    (nest / "Helpers.lua").write_text("return {ok=true}", encoding="utf-8")

    vscode = tmp_path / ".vscode"
    vscode.mkdir()
    (vscode / "settings.json").write_text(
        json.dumps({"lifeboatapi.stormworks.libs.libraryPaths": [str(external)]}),
        encoding="utf-8",
    )

    paths = discover_library_paths(tmp_path)
    assert any(p.resolve() == external.resolve() for p in paths)

    src = 'local H = require("Shared.Util.Helpers")'
    out = bundle_requires(src, tmp_path)
    assert "require" not in out
    assert "ok=true" in out


def test_unresolved_require_flagged():
    src = 'local x = require("Missing.Module")\nfunction onTick() end'
    errs = validate_minified(src, addon=False)
    assert any("Unresolved require" in e for e in errs)


def test_unresolved_require_ok_in_addon():
    src = 'local x = require("Missing.Module")\nfunction onTick() end'
    errs = validate_minified(src, addon=True)
    assert not any("Unresolved require" in e for e in errs)


def test_minify_with_build_libs(tmp_path: Path):
    mod = tmp_path / "_build" / "libs" / "LifeBoatAPI"
    mod.mkdir(parents=True)
    (mod / "Thing.lua").write_text(
        "local T={}\nfunction T:new() return setmetatable({}, self) end\nreturn T\n",
        encoding="utf-8",
    )
    main = (
        'local T = require("LifeBoatAPI.Thing")\n'
        "function onTick()\n"
        "  local o = T:new()\n"
        "  output.setNumber(1, 1)\n"
        "end\n"
    )
    result, stats = minify(main, level=3, root_dir=str(tmp_path))
    assert "require" not in result
    assert stats.semantic_ok, stats.semantic_errors
