"""Linter short-circuit false-positive regressions."""

from src.core.minifier import minify
from src.core.linter import lint_script


SEMI_GUIDED_SNIPPET = """
topdown = true
function onTick()
    guide = ((topdown) and (useAngle or useDirection)) and vecReflect(
        Vector(-(cmd.x+sin(wantedDirection*chooseDirectionSide)*useDirectionNum),
               -(cmd.y-cos(wantedDirection*chooseDirectionSide)*useDirectionNum),
               sin(wantedAngleRad)), cmd, 2) or cmd
end
"""

LEAD_INDICATOR_SNIPPET = """
function onTick()
    ldtc = dtc
end
"""


def test_semi_guided_dead_branch_not_flagged():
    errors = lint_script(SEMI_GUIDED_SNIPPET)
    undef = [e for e in errors if "Undefined global" in e]
    assert not undef, undef


def test_lead_indicator_nil_assign_not_flagged():
    errors = lint_script(LEAD_INDICATOR_SNIPPET)
    undef = [e for e in errors if "dtc" in e]
    assert not undef


def test_minify_semi_guided_semantic_ok():
    _, stats = minify(SEMI_GUIDED_SNIPPET, level=4)
    assert stats.semantic_ok, stats.semantic_errors
