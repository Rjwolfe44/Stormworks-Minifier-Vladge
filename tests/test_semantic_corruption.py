"""
Regression tests for semantic corruption bugs (while-scope, SW API props, floor, validator).
"""

from src.core.minifier import minify
from src.core.validate import validate_minified
from src.core.lexer import tokenize
from src.core.scope import build_scope_tree


WHILE_SORT_FIXTURE = """
function onDraw()
  local hits = {}
  local nH = 0
  for i = 1, 5 do
    nH = nH + 1
    hits[nH] = { brg = i, sx = i, sy = i }
  end
  for i = 2, nH do
    local k = hits[i]
    local j = i - 1
    while j >= 1 and hits[j].brg > k.brg do
      hits[j + 1] = hits[j]
      j = j - 1
    end
    hits[j + 1] = k
  end
  for i = 1, nH do
    local a = hits[i]
    screen.drawLine(0, 0, a.sx, a.sy)
  end
end
"""

MAP_API_FIXTURE = """
local s = screen
local mTS = map.mapToScreen
local drawMap = screen.drawMap
function onDraw()
  local w, h = s.getWidth() - 1, s.getHeight() - 1
  local cx, cy = math.floor(w / 2), math.floor(h / 2)
  drawMap(0, 0, 0.5)
  local sx, sy = mTS(0, 0, 0.5, w, h, 1, 2)
  s.drawLine(cx, cy, sx, sy)
end
"""

BRACKET_API_FIXTURE = """
local mTS = map["mapToScreen"]
function onDraw()
  mTS(0, 0, 1, 32, 32, 0, 0)
end
"""

FLOOR_FIXTURE = """
local floor = math.floor
function onDraw()
  local x = floor(3.7)
  screen.drawText(0, 0, tostring(x))
end
"""


class TestWhileSortLocals:
    def test_scope_tree_for_while_end_idx(self):
        """for-scope must end at the for's end, not the nested while's end."""
        from src.core.lexer import TT
        tokens = tokenize(WHILE_SORT_FIXTURE)
        root = build_scope_tree(tokens)
        assert root.children, "expected function scope under root"
        func = root.children[0]
        for_scopes = [
            c for c in func.children
            if c.start_idx >= 0 and tokens[c.start_idx].value == "for"
        ]
        assert len(for_scopes) >= 2
        sort_for = for_scopes[1]
        assert sort_for.end_idx > 0
        assert tokens[sort_for.end_idx].value == "end"
        # j and k live on the for scope (or a child that ends at/after post-while)
        assert "j" in sort_for.locals
        assert "k" in sort_for.locals
        j_idxs = [i for i, t in enumerate(tokens) if t.type == TT.NAME and t.value == "j"]
        assert any(sort_for.start_idx < ji <= sort_for.end_idx for ji in j_idxs)
        # All j uses in the sort for must be within end_idx (the bug closed early)
        assert all(
            ji <= sort_for.end_idx
            for ji in j_idxs
            if ji > sort_for.start_idx
        )

    def test_no_leftover_originals_l2(self):
        result, stats = minify(WHILE_SORT_FIXTURE, level=2)
        assert "hits" not in result
        assert "nH" not in result
        # Classic corruption patterns from the bug report
        assert "a[j+1]=k" not in result
        assert "=k end" not in result and "[j+" not in result
        assert stats.semantic_ok, stats.semantic_errors

    def test_no_leftover_originals_l3(self):
        result, stats = minify(WHILE_SORT_FIXTURE, level=3)
        assert "hits" not in result
        assert "nH" not in result
        assert stats.semantic_ok, stats.semantic_errors
        # User table keys/props are renamed consistently (brg/sx/sy gone together)
        assert "brg" not in result
        assert "sx" not in result
        assert "sy" not in result

    def test_no_leftover_originals_l4(self):
        result, stats = minify(WHILE_SORT_FIXTURE, level=4)
        assert "hits" not in result
        assert "nH" not in result
        assert stats.semantic_ok, stats.semantic_errors
        assert "brg" not in result

    def test_user_props_renamed_consistently(self):
        src = """
function onTick()
  local newangle = { yaw = 1, pitch = 2 }
  local a = newangle.yaw
  local b = newangle.pitch
  output.setNumber(1, a + b)
end
"""
        result, stats = minify(src, level=3)
        assert "yaw" not in result
        assert "pitch" not in result
        assert "newangle" not in result
        assert stats.semantic_ok, stats.semantic_errors
        # Keys and accesses share the same short names
        assert "{a=" in result or "{b=" in result
        assert ".a" in result or ".b" in result


class TestApiMapFields:
    def test_map_to_screen_survives_l3(self):
        result, stats = minify(MAP_API_FIXTURE, level=3)
        assert "mapToScreen" in result
        assert "drawMap" in result
        assert "map.a" not in result
        assert stats.semantic_ok, stats.semantic_errors

    def test_map_to_screen_survives_l4(self):
        result, stats = minify(MAP_API_FIXTURE, level=4)
        assert "mapToScreen" in result
        assert "drawMap" in result
        assert stats.semantic_ok, stats.semantic_errors


class TestBracketApiSafe:
    def test_bracket_api_l3(self):
        result, stats = minify(BRACKET_API_FIXTURE, level=3)
        assert 'map["mapToScreen"]' in result or "map['mapToScreen']" in result
        assert stats.semantic_ok, stats.semantic_errors


class TestFloorNotRewritten:
    def test_floor_kept_at_l4(self):
        result, stats = minify(FLOOR_FIXTURE, level=4)
        # Direct math.floor or aliased call — must not become (3.7)//1 from floor golf
        assert "//1" not in result or "math.floor" in result or "floor" in result
        # Stronger: the literal rewrite of floor(3.7) must not appear
        assert "(3.7)//1" not in result
        assert stats.semantic_ok, stats.semantic_errors

    def test_direct_math_floor_l4(self):
        src = "function onDraw() local x=math.floor(3.7) screen.drawText(0,0,tostring(x)) end"
        result, stats = minify(src, level=4)
        assert "math.floor" in result or ".floor" in result
        assert "(3.7)//1" not in result


class TestSemanticValidator:
    def test_clean_script_passes(self):
        result, stats = minify(WHILE_SORT_FIXTURE, level=2)
        assert stats.semantic_ok
        assert validate_minified(result) == []

    def test_undefined_global_flagged(self):
        broken = "function onDraw() screen.drawLine(0,0,j,k) end"
        errs = validate_minified(broken)
        assert any("Undefined global" in e and ("'j'" in e or "'k'" in e) for e in errs)

    def test_renamed_sw_api_flagged(self):
        broken = "function onDraw() map.a(0,0,1,32,32,0,0) end"
        errs = validate_minified(broken)
        assert any("map.a" in e or "Unknown or renamed API" in e for e in errs)

    def test_known_api_ok(self):
        ok = "function onDraw() local x,y=map.mapToScreen(0,0,1,32,32,0,0) end"
        assert validate_minified(ok) == []
