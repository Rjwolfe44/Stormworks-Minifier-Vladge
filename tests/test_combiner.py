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


def test_extra_paths_resolution(tmp_path: Path):
    external = tmp_path / "ext"
    mod = external / "Pack"
    mod.mkdir(parents=True)
    (mod / "Item.lua").write_text("return 42", encoding="utf-8")
    # root has no Pack/ — only extra_paths should resolve it
    out = bundle_requires(
        'local x = require("Pack.Item")',
        tmp_path,
        extra_paths=[external],
    )
    assert "require" not in out
    assert "return 42" in out


def test_nested_require_keeps_search_dirs(tmp_path: Path):
    """A required file's require() must still see project/_build/libs."""
    lib = tmp_path / "_build" / "libs" / "LifeBoatAPI"
    lib.mkdir(parents=True)
    (lib / "Core.lua").write_text("return {n=1}", encoding="utf-8")
    # Mid file lives under a subfolder; its require must not lose _build/libs
    mid = tmp_path / "src" / "app"
    mid.mkdir(parents=True)
    (mid / "boot.lua").write_text(
        'local C = require("LifeBoatAPI.Core")\nreturn C\n',
        encoding="utf-8",
    )
    main = 'local b = require("src.app.boot")\nfunction onTick() end\n'
    out = bundle_requires(main, tmp_path)
    assert "require" not in out
    assert "n=1" in out
    result, stats = minify(main, level=3, root_dir=str(tmp_path))
    assert "require" not in result
    assert stats.semantic_ok, stats.semantic_errors


def test_unresolved_require_flagged():
    src = 'local x = require("Missing.Module")\nfunction onTick() end'
    errs = validate_minified(src, addon=False)
    assert any("Unresolved require" in e for e in errs)
    assert any("Missing.Module" in e for e in errs)


def test_unresolved_require_ok_in_addon():
    src = 'local x = require("Missing.Module")\nfunction onTick() end'
    errs = validate_minified(src, addon=True)
    assert not any("Unresolved require" in e for e in errs)


def test_allow_require_skips_flag():
    src = 'local x = require("Missing.Module")\nfunction onTick() end'
    errs = validate_minified(src, allow_require=True)
    assert not any("Unresolved require" in e for e in errs)


def test_require_search_hint_in_message():
    src = 'require("Nope")\nfunction onTick() end'
    errs = validate_minified(src, require_search_hint="/proj, /proj/_build/libs")
    assert any("Searched: /proj" in e for e in errs)


def test_module_cache_hoisted_as_local(tmp_path: Path):
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "mod.lua").write_text("return {ok=1}", encoding="utf-8")
    out = bundle_requires('local m = require("lib.mod")', tmp_path)
    assert out.startswith("local __m0;")
    assert "if not __m0 then __m0 =" in out


def test_safe_props_keeps_user_fields():
    src = (
        "function onTick()\n"
        "  local t = { yaw = 1, pitch = 2 }\n"
        "  output.setNumber(1, t.yaw + t.pitch)\n"
        "end\n"
    )
    result, stats = minify(src, level=3, safe_props=True)
    assert "yaw" in result and "pitch" in result
    assert stats.semantic_ok, stats.semantic_errors
    aggressive, _ = minify(src, level=3, safe_props=False)
    assert "yaw" not in aggressive


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
    assert result.startswith("local ")  # hoisted module cache local(s)
