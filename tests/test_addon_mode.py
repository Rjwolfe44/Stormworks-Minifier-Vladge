"""Regression tests for mission-addon mode (131071 limit)."""

from __future__ import annotations

from src.core.addon_mode import ADDON_CHAR_LIMIT, MC_CHAR_LIMIT, finalize_addon_source
from src.core.minifier import CHAR_LIMIT, minify
from src.core.validate import validate_minified


ADDON_FIXTURE = """
g_savedata = {
  enabled = property.checkbox("Enable raids", true),
  difficulty = property.slider("Difficulty", 1, 10, 5, 1),
}
function onTick()
  local x = g_savedata.enabled
  if x then
    server.announce("[HR]", "tick")
  end
end
"""


def test_mc_default_limit_unchanged():
    assert CHAR_LIMIT == MC_CHAR_LIMIT == 8192
    result, stats = minify("function onTick() local hello_world=1 end", level=2)
    assert stats.char_limit == 8192
    assert stats.mode == "microcontroller"
    assert "hello" not in result or "a=" in result or "a =" in result  # renamed
    assert stats.under_limit


def test_addon_protects_g_savedata_and_property_lines():
    result, stats = minify(ADDON_FIXTURE, level=2, addon=True)
    assert stats.mode == "addon"
    assert stats.char_limit == ADDON_CHAR_LIMIT == 131071
    assert "g_savedata" in result
    assert "property.checkbox" in result
    assert "property.slider" in result
    assert "property.checkbox" in result.splitlines()[0] or any(
        ln.lstrip().startswith("property.checkbox") for ln in result.splitlines()
    )
    assert any(ln.lstrip().startswith("property.slider") for ln in result.splitlines())
    assert validate_minified(result) == []
    assert stats.semantic_ok
    assert stats.under_limit



def test_finalize_addon_source_breaks_property_calls():
    jammed = 'g_savedata={a=property.checkbox("A",true),b=property.slider("B",1,2,1,1)}'
    out = finalize_addon_source(jammed)
    assert "\nproperty.checkbox" in out or out.startswith("property.checkbox")
    assert "\nproperty.slider" in out


def test_addon_does_not_rename_g_savedata_at_l3():
    src = "g_savedata = { n = 1 }\nfunction onTick() local z = g_savedata.n end"
    result, stats = minify(src, level=3, addon=True)
    assert "g_savedata" in result
    assert stats.char_limit == ADDON_CHAR_LIMIT
