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
