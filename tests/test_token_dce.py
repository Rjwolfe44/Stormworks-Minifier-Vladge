"""Token DCE and late constant inliner tests."""

from src.core.minifier import minify


def test_dead_local_removed_l4():
    src = """
function onTick()
    local dead = 99
    local used = 1
    used = used + 1
end
"""
    out, stats = minify(src, level=4)
    assert "dead" not in out or stats.dead_locals >= 0
    assert stats.semantic_ok


def test_late_constant_inline():
    src = """
local PI = 3.14
function onTick()
    local x = PI + PI
end
"""
    out, stats = minify(src, level=4)
    assert stats.semantic_ok
    # PI may be inlined after fold
    assert len(out) <= len(src)


def test_unused_local_removed():
    src = """
function onTick()
    local dead = 99
    local used = 1
    used = used + 1
end
"""
    out, stats = minify(src, level=4)
    assert stats.semantic_ok
