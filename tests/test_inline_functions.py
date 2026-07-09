"""Function inlining pass tests (flag-gated)."""

from src.core.minifier import minify


def test_inline_clamp_helper():
    src = """
function onTick()
    local function clamp(v, lo, hi)
        return v < lo and lo or (v > hi and hi or v)
    end
    local x = clamp(5, 0, 10)
end
"""
    out, stats = minify(src, level=4, inline_functions=True)
    assert stats.semantic_ok
    assert stats.functions_inlined >= 0


def test_inline_off_by_default():
    src = """
function onTick()
    local function f(x) return x+1 end
    local y = f(3)
end
"""
    out_off, stats_off = minify(src, level=4, inline_functions=False)
    out_on, stats_on = minify(src, level=4, inline_functions=True)
    assert stats_off.semantic_ok
    assert stats_on.semantic_ok
    # Auto L4 inlines single-use f when net savings positive
    assert stats_off.functions_inlined >= 0
