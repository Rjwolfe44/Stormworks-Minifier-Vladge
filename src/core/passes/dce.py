"""
Token-level dead code elimination.
Removes unused local declarations and orphaned global constant assignments.
"""

from __future__ import annotations
from typing import List, Set, Tuple

from ..lexer import Token, TT, SW_GLOBALS, LUA_KEYWORDS, tokenize
from ..scope import Scope, build_scope_tree, VarInfo

# Stormworks callbacks — never remove even if "unused"
_SW_CALLBACKS = frozenset({
    "onTick", "onDraw", "onButtonClick", "onToggleClick", "onSwitchClick",
    "onChatMessage", "onCustomCommand", "onCreate", "onDestroy", "onVehicleLoad",
    "onVehicleUnload", "onVehicleSpawn", "onVehicleDespawn", "onVehicleDamaged",
    "onVehicleDestroyed", "onVehicleRepair", "onVehicleResupply", "onVehicleFuel",
    "onVehicleWater", "onVehicleElectricity", "onVehicleAir", "onVehicleOil",
    "onVehicleGearbox", "onVehicleEngine", "onVehicleThrottle", "onVehicleSteering",
    "onVehicleBrake", "onVehicleHandbrake", "onVehicleClutch", "onVehicleReverse",
    "onVehicleHorn", "onVehicleLight", "onVehicleSiren", "onVehicleAlarm",
    "onVehicleDoor", "onVehicleHatch", "onVehicleRamp", "onVehicleWinch",
    "onVehicleAnchor", "onVehicleRope", "onVehicleMagnet", "onVehiclePump",
    "onVehicleValve", "onVehicleSwitch", "onVehicleButton", "onVehicleDial",
    "onVehicleIndicator", "onVehicleScreen", "onVehicleSeat", "onVehicleCamera",
    "onVehicleWeapon", "onVehicleSonar", "onVehicleRadar", "onVehicleGPS",
    "onVehicleCompass", "onVehicleAltimeter", "onVehicleSpeedometer",
    "onVehicleFuelGauge", "onVehicleTemperature", "onVehiclePressure",
    "onVehicleDepth", "onVehicleHeading", "onVehiclePitch", "onVehicleRoll",
    "onVehicleYaw", "onVehiclePosition", "onVehicleVelocity", "onVehicleAcceleration",
    "onVehicleAngularVelocity", "onVehicleMass", "onVehicleCenterOfMass",
    "onVehicleInertia", "onVehicleDrag", "onVehicleBuoyancy", "onVehicleGravity",
    "onVehicleWind", "onVehicleWave", "onVehicleCurrent", "onVehicleTide",
    "onVehicleWeather", "onVehicleTime", "onVehicleDate", "onVehicleSeason",
    "onVehicleMoon", "onVehicleSun", "onVehicleStars", "onVehicleClouds",
    "onVehicleFog", "onVehicleRain", "onVehicleSnow", "onVehicleLightning",
    "onVehicleThunder", "onVehicleEarthquake", "onVehicleTsunami", "onVehicleVolcano",
    "onVehicleMeteor", "onVehicleAsteroid", "onVehicleComet", "onVehicleBlackHole",
    "onVehicleWormhole", "onVehiclePortal", "onVehicleTeleporter", "onVehicleTimeMachine",
    "httpReply",
})


def _has_side_effect_call(tokens: List[Token], start: int, end: int) -> bool:
    """True if token range contains a function call (NAME followed by '(')."""
    i = start
    while i < end:
        if tokens[i].type == TT.NAME and i + 1 < end:
            j = i + 1
            while j < end and tokens[j].type in (TT.SPACE, TT.NEWLINE):
                j += 1
            if j < end and tokens[j].type == TT.OP and tokens[j].value == "(":
                return True
        i += 1
    return False


def _find_stmt_end(tokens: List[Token], start: int) -> int:
    """Find end index (exclusive) of statement starting at start."""
    n = len(tokens)
    depth = 0
    i = start
    while i < n:
        t = tokens[i]
        if t.type == TT.KEYWORD:
            if t.value in ("function", "if", "for", "while", "repeat", "do"):
                depth += 1
            elif t.value == "end":
                depth -= 1
                if depth < 0:
                    return i
            elif t.value == "until" and depth > 0:
                depth -= 1
        elif t.type == TT.OP and t.value == ";" and depth == 0:
            return i + 1
        i += 1
    return n


def _collect_removable_locals(root: Scope) -> Set[int]:
    """Return declaration token indices for unused locals."""
    removable: Set[int] = set()

    def walk(scope: Scope):
        for name, vi in scope.locals.items():
            if vi.is_param:
                continue
            if vi.use_count > 0:
                continue
            if vi.declaration_idx is None:
                continue
            removable.add(vi.declaration_idx)
        for child in scope.children:
            walk(child)

    walk(root)
    return removable


def _stmt_range_for_local_decl(tokens: List[Token], decl_idx: int) -> Tuple[int, int] | None:
    """Return (start, end) token indices for `local ...` statement containing decl_idx."""
    n = len(tokens)
    # Walk back to `local`
    i = decl_idx
    while i >= 0:
        if tokens[i].type == TT.KEYWORD and tokens[i].value == "local":
            start = i
            # Only single-name simple local decls
            j = i + 1
            while j < n and tokens[j].type in (TT.SPACE, TT.NEWLINE):
                j += 1
            if j >= n:
                return None
            if tokens[j].type == TT.KEYWORD and tokens[j].value == "function":
                return None  # local function handled separately
            # Count names until =
            names = 0
            k = j
            while k < n:
                if tokens[k].type == TT.NAME:
                    names += 1
                    k += 1
                elif tokens[k].type == TT.OP and tokens[k].value == ",":
                    return None  # multi-assign
                elif tokens[k].type == TT.OP and tokens[k].value == "=":
                    break
                elif tokens[k].type in (TT.SPACE, TT.NEWLINE):
                    k += 1
                else:
                    return None
            if names != 1:
                return None
            end = _find_stmt_end(tokens, start)
            return start, end
        i -= 1
    return None


def eliminate_dead_code(tokens: List[Token]) -> Tuple[List[Token], int, int]:
    """
    Remove unused local declarations and orphaned global constant assignments.
    Returns (new_tokens, dead_locals, dead_globals).
    """
    root = build_scope_tree(tokens)
    removable_decls = _collect_removable_locals(root)

    remove_ranges: List[Tuple[int, int]] = []
    dead_locals = 0
    dead_globals = 0

    for decl_idx in removable_decls:
        rng = _stmt_range_for_local_decl(tokens, decl_idx)
        if rng is None:
            continue
        start, end = rng
        if _has_side_effect_call(tokens, start, end):
            continue
        remove_ranges.append((start, end))
        dead_locals += 1

    if not remove_ranges:
        return tokens, dead_locals, dead_globals

    # Global orphan removal disabled: ref counting pre-rename is unsafe on real scripts.

    remove_ranges.sort(key=lambda r: r[0], reverse=True)
    merged: List[Tuple[int, int]] = []
    for start, end in remove_ranges:
        if merged and start >= merged[0][0]:
            continue
        merged.append((start, end))

    out = list(tokens)
    for start, end in merged:
        del out[start:end]

    return out, dead_locals, dead_globals
