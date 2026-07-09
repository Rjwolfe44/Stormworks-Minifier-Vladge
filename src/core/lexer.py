"""
VladgeMinifier - Fast Regex-based Lua Lexer

Efficiently processes and tokenizes Lua source code into a structured token stream.
This lexical analysis is the foundational step for subsequent minification, 
scope resolution, and abstract syntax tree construction.
"""

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import List


class TT(Enum):
    """
    Enumeration of distinct token types identified by the lexer.
    Categories include Literals, Keywords, Operators, Whitespace, Comments, and End-of-File.
    """
    # Literals
    NUMBER    = auto()
    STRING    = auto()
    NAME      = auto()
    # Keywords
    KEYWORD   = auto()
    # Operators / punctuation
    OP        = auto()
    # Whitespace / structure
    NEWLINE   = auto()
    SPACE     = auto()
    # Comments
    COMMENT   = auto()
    LONGCOMMENT = auto()
    # Long strings
    LONGSTRING = auto()
    # End of file
    EOF       = auto()


# A static, immutable set comprising all reserved keywords in the Lua 5.3 language specification.
LUA_KEYWORDS = frozenset({
    "and", "break", "do", "else", "elseif", "end",
    "false", "for", "function", "goto", "if", "in",
    "local", "nil", "not", "or", "repeat", "return",
    "then", "true", "until", "while",
})

# Immutable Stormworks and Lua global namespace identifiers.
# These top-level APIs must never be structurally renamed to preserve engine compatibility.
SW_GLOBALS = frozenset({
    # ── Stormworks API table names ────────────────────────────────────────────
    "input", "output", "screen", "map", "math", "property",
    "async", "http", "server", "matrix", "ui", "peer",
    # ── Lua standard library table names ─────────────────────────────────────
    "string", "table", "coroutine", "os", "io", "debug", "utf8",
    # ── Lua built-in functions (standalone, not method calls) ─────────────────
    "pairs", "ipairs", "next", "select",
    "error", "assert", "pcall", "xpcall", "rawget", "rawset",
    "tostring", "tonumber", "setmetatable", "getmetatable",
    "unpack", "load", "loadstring", "rawequal", "rawlen",
    "require", "dofile", "loadfile", "collectgarbage",
    "print", "warn", "self", "_G", "_VERSION", "type",
    # ── Stormworks callbacks — must never be renamed ──────────────────────────
    "onTick", "onDraw", "onCreate", "onDestroy",
    "onKeyboard", "onHTTP", "onCustomCommand", "httpReply",
    "onAction", "onPlayerJoin", "onPlayerLeave", "onPlayerDie",
    "onPlayerRespawn", "onPlayerSit", "onPlayerUnsit",
    "onCharacterSit", "onCharacterUnsit", "onCharacterPickup",
    "onButtonPress", "onSpawnAddonComponent",
    "onVehicleSpawn", "onVehicleDespawn", "onVehicleLoad",
    "onVehicleUnload", "onVehicleTeleport",
    "onObjectLoad", "onObjectUnload",
    "onFireExtinguished", "onForestFireSpawned", "onForestFireExtinguished",
    "onTornado", "onMeteor", "onTsunami", "onWhirlpool", "onVolcano",
})

# Stormworks and Lua API internal property accessors (e.g., `math.pi`).
# These names are safely renameable when declared as independent local variables, 
# but are strictly preserved when accessed as table members via '.' or ':' notation.
SW_API_PROPERTIES = frozenset({
    # ── math library members ──────────────────────────────────────────────────
    "pi", "huge", "maxinteger", "mininteger",
    "abs", "ceil", "floor", "sqrt", "sin", "cos", "tan",
    "asin", "acos", "atan",
    "exp", "log", "log10",
    "max", "min", "fmod", "modf",
    "pow", "random", "randomseed",
    "sinh", "cosh", "tanh",
    "deg", "rad",
    "tointeger", "ldexp", "frexp",
    # ── string library members ────────────────────────────────────────────────
    "format", "sub", "len", "find", "match", "gmatch", "gsub",
    "byte", "char", "rep", "reverse", "upper", "lower",
    "dump", "packsize", "pack", "unpack",
    # ── table library members ─────────────────────────────────────────────────
    "insert", "remove", "concat", "sort", "move",
    # ── io / os / coroutine library members ──────────────────────────────────
    "read", "write", "open", "close", "lines", "flush",
    "time", "clock", "date", "exit", "getenv", "difftime",
    "create", "resume", "yield", "status", "wrap", "isyieldable", "running",
    # ── input / output / property members ────────────────────────────────────
    "getNumber", "getBool", "getText", "getAngle",
    "setNumber", "setBool", "setText",
    "slider", "checkbox",
    "x", "y", "z",
    # ── screen members ────────────────────────────────────────────────────────
    "setColor", "drawClear",
    "drawRect", "drawRectF",
    "drawCircle", "drawCircleF",
    "drawLine", "drawTriangle", "drawTriangleF",
    "drawText", "drawTextBox",
    "drawImage", "drawTexture",
    "drawMap",
    "getWidth", "getHeight",
    "getMapColorAlpha", "setMapColorAlpha",
    "setMapColorOcean", "setMapColorShallows", "setMapColorLand",
    "setMapColorGrass", "setMapColorSand", "setMapColorSnow",
    "drawCustomImage",
    # ── map members ───────────────────────────────────────────────────────────
    "mapToScreen", "screenToMap",
    # ── matrix members ───────────────────────────────────────────────────────
    "position", "multiply", "rotationX", "rotationY", "rotationZ",
    "translation", "identity", "lookAt",
    # ── server/http/async members (addon API) ─────────────────────────────────
    "announce", "getPlayerPos", "setCharacterData", "reviveCharacter",
    "getMapID", "addMapObject", "removeMapObject", "removePopup",
    "getVehiclePos", "setVehicleKeypad", "getVehicleDial",
    "getVehicleBattery", "setVehicleBattery", "getVehicleComponents",
    "getPlayerName", "getPlayerCharacterID", "getCharacterVehicle",
    "spawnVehicle", "despawnVehicle",
    "setPopup", "addPopup",
    "getAddonData", "getAddonIndex",
    "get", "fetch", "getPort",
})



@dataclass(slots=True)
class Token:
    type: TT
    value: str
    pos: int  # byte offset in source
    is_global: bool = False

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r})"


# ─── Token patterns (order matters!) ────────────────────────────────────────
_LONG_OPEN  = re.compile(r'\[(?P<eq>=*)\[')
_LONG_CLOSE = re.compile(r'\](?P<eq>=*)\]')

# Precompiled unified regular expression pattern for maximum parsing throughput.
# Order is critical: complex/multi-character tokens must match prior to single characters.
_TOKEN_RE = re.compile(
    r"""
    # Long comments  --[=*[ ... ]=*]
    (?P<longcomment>--\[(?P<lceq>=*)\[.*?\](?P=lceq)\])

    # Short comments  -- ...
    |(?P<comment>--[^\n]*)

    # Long strings  [=*[ ... ]=*]
    |(?P<longstring>\[(?P<lseq>=*)\[.*?\](?P=lseq)\])

    # Double-quoted strings
    |(?P<dqstring>"(?:[^"\\]|\\.)*")

    # Single-quoted strings
    |(?P<sqstring>'(?:[^'\\]|\\.)*')

    # Numbers (hex, float, int)
    |(?P<number>0[xX][0-9a-fA-F]+(?:\.[0-9a-fA-F]*)?(?:[pP][+-]?\d+)?
               |\d+(?:\.\d*)?(?:[eE][+-]?\d+)?
               |\.\d+(?:[eE][+-]?\d+)?)

    # Identifiers / keywords
    |(?P<name>[a-zA-Z_]\w*)

    # 3-char operators
    |(?P<op3>\.\.\.)

    # 2-char operators
    |(?P<op2>==|~=|<=|>=|\.\.|\:\:|<<|>>|//|\-\-)

    # 1-char operators / punctuation
    |(?P<op1>[+\-*/%^#&|~<>=(){}\[\];:,.])

    # Newlines (track them for spacing decisions)
    |(?P<newline>\r?\n)

    # Spaces / tabs
    |(?P<space>[ \t]+)
    """,
    re.VERBOSE | re.DOTALL,
)


def tokenize(source: str) -> List[Token]:
    """
    Tokenizes raw Lua source code into a discrete sequence of structural tokens.
    
    This function constitutes the hot path of the minifier and is heavily optimised 
    for single-pass execution throughput.
    
    Args:
        source (str): The raw Lua source code string to evaluate.
        
    Returns:
        List[Token]: An ordered sequence of parsed Tokens concluding with an EOF token.
    """
    tokens: List[Token] = []
    pos = 0
    src_len = len(source)

    while pos < src_len:
        m = _TOKEN_RE.match(source, pos)
        if m is None:
            # Skip unrecognised character (shouldn't happen with valid Lua)
            pos += 1
            continue

        gd = m.lastgroup
        val = m.group()

        if gd in ("longcomment",):
            tokens.append(Token(TT.LONGCOMMENT, val, pos))
        elif gd == "comment":
            tokens.append(Token(TT.COMMENT, val, pos))
        elif gd == "longstring":
            tokens.append(Token(TT.LONGSTRING, val, pos))
        elif gd in ("dqstring", "sqstring"):
            tokens.append(Token(TT.STRING, val, pos))
        elif gd == "number":
            tokens.append(Token(TT.NUMBER, val, pos))
        elif gd == "name":
            tt = TT.KEYWORD if val in LUA_KEYWORDS else TT.NAME
            tokens.append(Token(tt, val, pos))
        elif gd in ("op3", "op2", "op1"):
            tokens.append(Token(TT.OP, val, pos))
        elif gd == "newline":
            tokens.append(Token(TT.NEWLINE, val, pos))
        elif gd == "space":
            tokens.append(Token(TT.SPACE, val, pos))

        pos = m.end()

    tokens.append(Token(TT.EOF, "", pos))
    return tokens


def tokens_to_source(tokens: List[Token]) -> str:
    """
    Reconstructs the source code representation directly from a sequence of tokens.
    
    Args:
        tokens (List[Token]): The ordered stream of code tokens.
        
    Returns:
        str: Reassembled executable source code.
    """
    return "".join(t.value for t in tokens if t.type != TT.EOF)
