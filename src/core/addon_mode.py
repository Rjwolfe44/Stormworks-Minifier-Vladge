"""
Addon / mission-script helpers for VladgeMinifier.

Stormworks mission addons use a different ceiling and a few sacred names
that microcontroller scripts do not care about.
"""

from __future__ import annotations

import re
from typing import Final

# Stormworks mission script.lua hard limit (confirmed in-game / SW forums).
ADDON_CHAR_LIMIT: Final[int] = 131071
MC_CHAR_LIMIT: Final[int] = 8192

# Engine-owned / must never rename in addon scripts.
ADDON_PROTECTED_GLOBALS: Final[frozenset[str]] = frozenset({
    "g_savedata",
    # Common addon lifecycle callbacks not all listed in SW_GLOBALS historically
    "onVehicleDamaged",
    "onVehicleTeleport",
    "onGroupSpawn",
    "onGroupDespawn",
    "onAddonStart",
    "httpReply",
})

# Extra server.* / matrix.* names commonly used by addons (safe allowlist for validate).
ADDON_SERVER_API_PROPERTIES: Final[frozenset[str]] = frozenset({
    "httpGet", "httpPost", "httpReply",
    "announce", "notify", "getPlayers", "getPlayerPos", "getPlayerName",
    "getPlayerCharacterID", "getCharacterVehicle", "setCharacterData",
    "setCharacterSeated", "getCharacterData", "despawnObject", "spawnObject",
    "spawnVehicle", "despawnVehicle", "despawnVehicleGroup",
    "getVehiclePos", "getVehicleData", "getVehicleGroup", "getVehicleSimulating",
    "getVehicleLocal", "moveGroupSafe", "setVehiclePosSafe",
    "setVehicleKeypad", "getVehicleDial", "setVehicleButton",
    "setAITarget", "setAIState", "setAITargetVehicle", "getAITarget",
    "addMapObject", "removeMapObject", "removeMapID", "removeMapLine",
    "addMapLine", "getMapID", "setCurrency", "getCurrency", "getResearchPoints",
    "spawnExplosion", "getOceanTransform", "getOceanFloor", "isInChannel",
    "getAddonIndex", "getLocationIndex", "getLocationData", "spawnAddonLocation",
    "getPathForVehicle", "getTileTransform",
    # matrix extras often used by HR/UFC-style scripts
    "distance", "inverse", "transpose", "rotationToFaceXZ",
})

_PROP_SETTING_RE = re.compile(r"(?<!\n)(property\.(?:slider|checkbox)\s*\()")


def finalize_addon_source(source: str) -> str:
    """
    Mission UI reads property.slider / property.checkbox from script text.
    Keep each call on its own line (same rule as the working PS1 minifier).
    """
    src = source.replace("\r\n", "\n").replace("\r", "\n")
    src = _PROP_SETTING_RE.sub(r"\n\1", src)
    src = re.sub(r"\n{3,}", "\n\n", src)
    return src.lstrip("\n")
