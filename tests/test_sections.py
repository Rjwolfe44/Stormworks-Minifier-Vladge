from src.core.passes.section_stripper import strip_dead_sections

def test_strip_dead_sections():
    source = '''
---@section MyClass
local MyClass = {}
function MyClass:new() return {} end
---@endsection

local x = 10
'''
    result, count = strip_dead_sections(source)
    # MyClass is not referenced outside its block, so it should be stripped
    assert count == 1
    assert "MyClass" not in result
    assert "local x = 10" in result

def test_keep_referenced_sections():
    source = '''
---@section MyClass
local MyClass = {}
function MyClass:new() return {} end
---@endsection

local obj = MyClass:new()
'''
    result, count = strip_dead_sections(source)
    # MyClass IS referenced, so it must be kept
    assert count == 0
    assert "MyClass:new" in result

def test_recursive_stripping():
    source = '''
---@section Dependency
local Dependency = {}
---@endsection

---@section Manager
local Manager = {}
function Manager:init()
    return Dependency
end
---@endsection

local active = true
'''
    result, count = strip_dead_sections(source)
    # Manager is not referenced outside its block, so it gets stripped.
    # ONCE Manager is stripped, Dependency is no longer referenced anywhere either!
    # So Dependency should ALSO be stripped iteratively.
    assert count == 2
    assert "Dependency" not in result
    assert "Manager" not in result
    assert "local active = true" in result
