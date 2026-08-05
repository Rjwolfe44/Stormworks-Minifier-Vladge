"""Parse gate verification tests."""

from src.core.validate import validate_minified
from tests.helpers_verify import check_parse, verify_minified


def test_parse_error_detected():
    errors = check_parse("function onTick( end")
    assert errors


def test_valid_lua_parses():
    assert not check_parse("function onTick() end")


def test_validate_includes_parse():
    errors = validate_minified("local x = (")
    assert any("Parse error" in e for e in errors)


def test_verify_minified_clean():
    assert not verify_minified("function onTick() end")
