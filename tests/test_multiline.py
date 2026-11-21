"""Multiline output mode tests."""

from src.core.minifier import minify
from tests.helpers_verify import check_parse, verify_minified


SAMPLE = """
function onTick()
    local x = 1
    if x > 0 then
        x = x + 1
    end
end
"""


def test_multiline_statements_has_newlines():
    out, stats = minify(SAMPLE, level=2, multiline="statements")
    assert "\n" in out
    assert "\n\n\n" not in out
    assert len(out) < len(SAMPLE)
    assert stats.semantic_ok


def test_multiline_singleline_no_newlines():
    out, stats = minify(SAMPLE, level=2, multiline=False)
    assert "\n" not in out.strip() or out.count("\n") == 0
    assert stats.semantic_ok


def test_multiline_preserve_parses():
    out, stats = minify(SAMPLE, level=2, multiline="preserve")
    assert not check_parse(out)
    assert stats.semantic_ok


def test_multiline_verify_minified():
    out, _ = minify(SAMPLE, level=4, multiline="statements")
    assert not verify_minified(out)


# ── Regression: "Keep line breaks" (statements mode) bunched statements ──────
# Reported 2026-11-18: at Strip/Standard, function bodies came out on one line
# (`function onDraw();screen.a();screen.b()end`) and `elseif` was split from
# its condition.

TRICKY = """
local t = {}
function onTick()
    local a = input.getNumber(1)
    local b = input.getNumber(2)
    t.x = a + b
    if a > b then
        t.y = 1
    elseif a < b then
        t.y = 2
    else
        t.y = 3
    end
    do
        local z = a * 2
        output.setNumber(1, z)
    end
    repeat
        a = a - 1
    until a < 0
    local ok = run(function() t.p = 1 t.q = 2 end)
    local cfg = { f = function(v) local w = v * 2 return w end, n = 3 }
    print "str call"
    t:method(1)
    output.setNumber(2, cfg.f(a))
end

function onDraw()
    screen.setColor(255, 0, 0)
    screen.drawText(1, 1, "hi")
    screen.drawRect(0, 0, 10, 10)
end
"""


def _sig(src):
    from src.core.lexer import tokenize, TT
    return [
        (t.type, t.value) for t in tokenize(src)
        if t.type not in (TT.SPACE, TT.NEWLINE, TT.EOF)
        and not (t.type == TT.OP and t.value == ";")
    ]


def test_statements_one_statement_per_line():
    out, stats = minify(TRICKY, level=1, multiline="statements")
    lines = out.split("\n")
    for stmt in (
        "screen.setColor(255,0,0)",
        'screen.drawText(1,1,"hi")',
        "screen.drawRect(0,0,10,10)",
        "elseif a<b then",
        "t.p=1",
        "t.q=2",
        "until a<0",
        "end",
    ):
        assert stmt in lines, f"{stmt!r} not on its own line:\n{out}"
    assert stats.semantic_ok


def test_statements_same_tokens_as_singleline():
    """Line breaks may only replace separators: the code itself is unchanged."""
    for level in (1, 2, 3):
        one, _ = minify(TRICKY, level=level)
        ml, stats = minify(TRICKY, level=level, multiline="statements")
        assert _sig(ml) == _sig(one), f"L{level}"
        assert not verify_minified(ml), f"L{level}"
        assert stats.semantic_ok


def test_statements_never_breaks_before_call_paren():
    # A newline before `(` after a value would invite Lua's call ambiguity.
    src = "local f = g\n(h or g)(1)\nx = f 'a'\n"
    out, _ = minify(src, level=1, multiline="statements")
    assert "\n(" not in out
    assert _sig(out) == _sig(minify(src, level=1)[0])
