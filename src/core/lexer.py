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
    "httpReply",
    "onAction",
    "onAddonStart",
    "onButtonPress",
    "onCharacterPickup",
    "onCharacterSit",
    "onCharacterUnsit",
    "onChatMessage",
    "onClearOilSpill",
    "onCreate",
    "onCreaturePickup",
    "onCreatureSit",
    "onCreatureUnsit",
    "onCustomCommand",
    "onDestroy",
    "onDraw",
    "onEquipmentDrop",
    "onEquipmentPickup",
    "onFireExtinguished",
    "onForestFireExtinguished",
    "onForestFireSpawned",
    "onGroupDespawn",
    "onGroupSpawn",
    "onHTTP",
    "onKeyboard",
    "onMeteor",
    "onObjectLoad",
    "onObjectUnload",
    "onOilSpill",
    "onPlayerDie",
    "onPlayerJoin",
    "onPlayerLeave",
    "onPlayerRespawn",
    "onPlayerSit",
    "onPlayerUnsit",
    "onSpawnAddonComponent",
    "onTick",
    "onToggleMap",
    "onTornado",
    "onTsunami",
    "onVehicleDamaged",
    "onVehicleDespawn",
    "onVehicleLoad",
    "onVehicleSpawn",
    "onVehicleTeleport",
    "onVehicleUnload",
    "onVolcano",
    "onWhirlpool",
    # ── Mission addon reserved ────────────────────────────────────────────────
    "g_savedata",
})



# Stormworks and Lua API internal property accessors (e.g., `math.pi`).
# These names are safely renameable when declared as independent local variables, 
# but are strictly preserved when accessed as table members via '.' or ':' notation.
SW_API_PROPERTIES = frozenset({
    # Generated from Cuh4 StormworksAddonLuaDocumentation intellisense.lua
    # plus microcontroller / Lua stdlib members. Do not rename these on SW receivers.
    "abs", "acos", "addAdmin", "addAuth", "addDamage", "addMapLabel",
    "addMapLine", "addMapObject", "addPopup", "announce", "asin", "atan",
    "banPlayer", "byte", "cancelGerstner", "ceil", "char", "checkbox",
    "cleanVehicles", "clearOilSpill", "clearRadiation", "clock", "close", "command",
    "concat", "cos", "cosh", "create", "createPopup", "date",
    "deg", "despawnObject", "despawnVehicle", "despawnVehicleGroup", "difftime", "distance",
    "dlcArid", "dlcSpace", "dlcWeapons", "drawCircle", "drawCircleF", "drawClear",
    "drawCustomImage", "drawImage", "drawLine", "drawMap", "drawRect", "drawRectF",
    "drawText", "drawTextBox", "drawTexture", "drawTriangle", "drawTriangleF", "dump",
    "exit", "exp", "fetch", "find", "floor", "flush",
    "fmod", "format", "frexp", "get", "getAITarget", "getAddonCount",
    "getAddonData", "getAddonIndex", "getAddonPath", "getAngle", "getAstroPos", "getBool",
    "getCharacterData", "getCharacterItem", "getCharacterVehicle", "getCurrency", "getDate", "getDateValue",
    "getFireData", "getFishData", "getFishHotspots", "getGameSetting", "getGameSettings", "getHeight",
    "getLocationComponentData", "getLocationData", "getLocationIndex", "getMapColorAlpha", "getMapID", "getNumber",
    "getObjectData", "getObjectPos", "getObjectSimulating", "getOceanFloor", "getOceanTransform", "getOilDeposits",
    "getOilSpill", "getPlayerCharacterID", "getPlayerLookDirection", "getPlayerName", "getPlayerPos", "getPlayers",
    "getPort", "getResearchPoints", "getSeasonalEvent", "getStartTile", "getText", "getTile",
    "getTileInventory", "getTilePurchased", "getTileTransform", "getTime", "getTimeMillisec", "getTutorial",
    "getVehicleBattery", "getVehicleButton", "getVehicleComponents", "getVehicleData", "getVehicleDial", "getVehicleFireCount",
    "getVehicleGroup", "getVehicleHopper", "getVehicleLocal", "getVehiclePos", "getVehicleRopeHook", "getVehicleSeat",
    "getVehicleSign", "getVehicleSimulating", "getVehicleTank", "getVehicleWeapon", "getVehiclesByName", "getVideoTutorial",
    "getVolcanos", "getWeather", "getWidth", "getZones", "getenv", "gmatch",
    "gsub", "httpGet", "httpReply", "huge", "identity", "insert",
    "inverse", "invert", "isDev", "isInTransformArea", "isInZone", "isLocationClear",
    "isyieldable", "kickPlayer", "killCharacter", "ldexp", "len", "lines",
    "log", "log10", "lookAt", "lower", "mapToScreen", "match",
    "max", "maxinteger", "min", "mininteger", "modf", "move",
    "moveGroup", "moveGroupSafe", "moveVehicle", "moveVehicleSafe", "multiply", "multiplyXYZW",
    "notify", "open", "pack", "packsize", "pathfind", "pathfindOcean",
    "pi", "position", "pow", "pressVehicleButton", "rad", "random",
    "randomseed", "read", "remove", "removeAdmin", "removeAuth", "removeMapID",
    "removeMapLabel", "removeMapLine", "removeMapObject", "removePopup", "rep", "resetVehicleState",
    "resume", "reverse", "reviveCharacter", "rotationToFaceXZ", "rotationX", "rotationY",
    "rotationZ", "running", "save", "screenToMap", "setAICharacterTargetTeam", "setAICharacterTeam",
    "setAIState", "setAITarget", "setAITargetCharacter", "setAITargetVehicle", "setAIVehicleTeam", "setAudioMood",
    "setBool", "setCharacterData", "setCharacterItem", "setCharacterSeated", "setCharacterTooltip", "setColor",
    "setCreatureMoveTarget", "setCurrency", "setFireData", "setGameSetting", "setGroupPos", "setGroupPosSafe",
    "setMapColorAlpha", "setMapColorGrass", "setMapColorLand", "setMapColorOcean", "setMapColorSand", "setMapColorShallows",
    "setMapColorSnow", "setNumber", "setObjectPos", "setOilSpill", "setPlayerPos", "setPopup",
    "setPopupScreen", "setSeated", "setText", "setTileInventory", "setTutorial", "setVehicleBattery",
    "setVehicleEditable", "setVehicleHopper", "setVehicleInvulnerable", "setVehicleKeypad", "setVehiclePos", "setVehiclePosSafe",
    "setVehicleSeat", "setVehicleShowOnMap", "setVehicleTank", "setVehicleTooltip", "setVehicleTransponder", "setVehicleWeapon",
    "setWeather", "sin", "sinh", "slider", "sort", "spawnAddonComponent",
    "spawnAddonLocation", "spawnAddonVehicle", "spawnAnimal", "spawnCharacter", "spawnCreature", "spawnEquipment",
    "spawnExplosion", "spawnFire", "spawnMeteor", "spawnMeteorShower", "spawnNamedAddonLocation", "spawnObject",
    "spawnThisAddonLocation", "spawnTornado", "spawnTsunami", "spawnVehicle", "spawnVehicleRope", "spawnVolcano",
    "spawnWhirlpool", "sqrt", "status", "sub", "tan", "tanh",
    "time", "tointeger", "translation", "transpose", "unpack", "upper",
    "wrap", "write", "x", "y", "yield", "z",
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
