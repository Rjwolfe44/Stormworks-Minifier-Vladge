# VladgeMinifier

A Stormworks Lua minifier that actually fits the **8192** character limit — and tries hard not to break your script while doing it.

**Current release: [v2.3.5](https://github.com/Rjwolfe44/Stormworks-Minifier-Vladge/releases/tag/v2.3.5)**

<p align="center">
  <a href="https://github.com/Rjwolfe44/Stormworks-Minifier-Vladge/releases/latest"><img alt="Download latest" src="https://img.shields.io/github/v/release/Rjwolfe44/Stormworks-Minifier-Vladge?style=for-the-badge&label=Download&color=2ea44f"></a>
  &nbsp;
  <a href="https://github.com/Rjwolfe44/Stormworks-Minifier-Vladge/releases/download/v2.3.5/VladgeMinifier-v2.3.5.zip"><img alt="Windows zip" src="https://img.shields.io/badge/Windows-ZIP-0A66C2?style=for-the-badge&logo=windows&logoColor=white"></a>
</p>

<p align="center">
  <strong><a href="https://github.com/Rjwolfe44/Stormworks-Minifier-Vladge/releases/latest">⬇ Download the latest release</a></strong>
  ·
  <a href="https://github.com/Rjwolfe44/Stormworks-Minifier-Vladge/releases/download/v2.3.5/VladgeMinifier-v2.3.5.zip">Direct zip (v2.3.5)</a>
</p>

---

## Why this exists

Stormworks microcontrollers hard-cap scripts at **8192 characters**. Real vehicle code — guidance, datalink, CIWS, shared `require()` libs — blows past that fast.

VladgeMinifier is built for that ceiling: strip, rename, pack, and validate, with levels from “just delete comments” to full Ultimate compression. It ships as a Windows GUI plus a CLI you can wire into **Cursor / VS Code**.

---

## Quick start

1. Grab the [latest Windows zip](https://github.com/Rjwolfe44/Stormworks-Minifier-Vladge/releases/latest)
2. Extract anywhere (keep the whole folder — GUI and CLI share `_internal`)
3. Run `VladgeMinifier.exe`
4. Drop a `.lua` file in, pick a level, minify
5. Paste into Stormworks (or use **Install to Editor** for one-key minify → clipboard)

Auto-update is built in: when a newer GitHub release exists, the app offers to download and install it.

---

## Minify levels

| Level | Name | What it does |
|------:|------|----------------|
| **1** | Strip Only | Comments, whitespace, number cleanup |
| **2** | Standard | + rename locals |
| **3** | Aggressive | + rename globals / user properties, API aliases *(default)* |
| **4** | Ultimate | + DCE, constant inline, packing, dedup, smart aliases, and more — falls back to L3 if L4 would grow |

Stormworks callbacks (`onTick`, `onDraw`, …) and API tables (`screen`, `map`, `input`, …) are never renamed. Property names on those APIs stay intact (`map.mapToScreen`, not `map.a`).

After minify you get a clear status:

- **`[OK]`** — parses clean, under the limit
- **`[BROKEN]`** — semantic / undefined refs (don’t paste that into a vehicle)
- **Over limit** — still over 8192 after compression

---

## GUI features

- Live minify with char count vs 8192
- **Keep line breaks** — readable minified output when you want it
- **Inline funcs** — optional L4 function inlining
- Drag-and-drop `.lua`
- Watch mode — remminify when the file changes
- Batch folder minify
- **Install to Editor** — Cursor / VS Code tasks + keybinds (no copying megabytes into your project)
- Sprite → Lua packing utility
- Deploy into microcontroller XML when you point it at your vehicle folder
- Built-in updater from GitHub Releases

### Editor shortcuts (after Install to Editor)

With a `.lua` file focused:

| Shortcut | Action |
|----------|--------|
| **Ctrl+Alt+M** | Minify → **clipboard** (your chosen paste level) |
| **Ctrl+Alt+Shift+M** | Pick any Vladge preset (readable save, batch, …) |

Re-run **Install to Editor** on an older project once to migrate broken leftover CLI copies out of `.vscode/`.

---

## CLI

The zip includes `vladgeminifier-cli.exe` next to the GUI.

```bat
vladgeminifier-cli.exe myscript.lua --level 4
vladgeminifier-cli.exe myscript.lua --level 4 --clipboard --no-save --quiet
vladgeminifier-cli.exe . --batch --level 4
```

Useful flags:

| Flag | Meaning |
|------|---------|
| `--level 1..4` | Minify strength (default 3) |
| `--clipboard` | Copy result to clipboard |
| `--no-save` | Don’t write `_minified/` (great with clipboard) |
| `--multiline statements\|preserve` | Keep readable line breaks |
| `--inline-functions` | More aggressive L4 inlining |
| `--deploy <dir>` | Inject into microcontroller XML / copy out |
| `--batch` | Process a whole folder |
| `--quiet` | Stats off |

---

## What’s under the hood

At a high level, Ultimate mode can:

- Bundle `require()` libraries and shake unused exports
- Rename locals (and user table keys) to shortest safe names
- Alias hot Stormworks API calls when it saves characters
- Deduplicate repeated strings / literals
- Dead-code eliminate unused locals and unreachable helpers
- Pack common structures (defaults, vectors, property tables) when the result still parses
- Validate with a real Lua parse + Stormworks-aware semantic check

If Ultimate ever produces *larger* output than Aggressive, it keeps Aggressive. Size alone isn’t success — broken Lua isn’t “smaller.”

---

## Build from source

```bat
git clone https://github.com/Rjwolfe44/Stormworks-Minifier-Vladge.git
cd Stormworks-Minifier-Vladge
build.bat
```

Output lands in `_export/VladgeMinifier/` (same layout as the release zip).

Needs **Python 3.10+** and the packages in `requirements.txt`. Tests: `python -m pytest tests/ -q`.

---

## Links

- **[Latest download](https://github.com/Rjwolfe44/Stormworks-Minifier-Vladge/releases/latest)**
- **[v2.3.5 zip](https://github.com/Rjwolfe44/Stormworks-Minifier-Vladge/releases/download/v2.3.5/VladgeMinifier-v2.3.5.zip)**
- **[All releases](https://github.com/Rjwolfe44/Stormworks-Minifier-Vladge/releases)**
- **[Source](https://github.com/Rjwolfe44/Stormworks-Minifier-Vladge)**

---

Made for people who live in the Stormworks Lua editor and are tired of fighting the 8192 wall.

See [LICENSE](LICENSE) for usage terms.
