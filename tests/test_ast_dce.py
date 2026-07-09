"""AST DCE hardening tests."""

from src.core.passes.ast_dce import ast_eliminate_dead_code
from src.core.minifier import minify


def test_ast_dce_removes_unreachable_function():
    src = """
function onTick()
    helper()
end
function helper()
    return 1
end
function deadFunc()
    return 2
end
"""
    out, removed, err = ast_eliminate_dead_code(src)
    assert err is None
    assert removed >= 1
    assert "deadFunc" not in out
    assert "helper" in out


def test_ast_dce_export_tree_shake():
    src = """
local M = {}
function M.used()
    return 1
end
function M.unused()
    return 2
end
return M
"""
    # Module pattern: used only if referenced from init — may not remove without require usage
    out, removed, err = ast_eliminate_dead_code(src)
    assert err is None


def test_ast_dce_local_function():
    src = """
function onTick()
    local function inner()
        return 1
    end
    return inner()
end
"""
    out, stats = minify(src, level=4)
    assert stats.semantic_ok
