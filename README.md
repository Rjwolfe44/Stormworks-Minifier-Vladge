# VladgeMinifier

**Version:** 2.2.0
**Target Engine:** Stormworks: Build and Rescue

VladgeMinifier is an aggressive, AST-aware Lua minification and obfuscation pipeline engineered specifically for the strict environment constraints of Stormworks. It employs multi-pass token analysis, static macro-aliasing, and a greedy slot-allocator variable renaming system to maximize logic density within the hard 8,192-character execution ceiling.

## Architecture Pipeline

The minification core utilizes a deterministic, sequential pass system to aggressively reduce the byte-size footprint of your code:

- **Modular Bundler & Tree Shaking**: Automatically resolves and bundles external Lua libraries using `require()` syntax. Natively traces references within exported modules, executing true AST-level tree-shaking to eliminate uncalled library functions and drastically reduce character counts.
- **Token Lexing & Scope Analysis**: Builds a full abstract scope tree, tracking global namespaces and ensuring nested local scopes don't suffer variable shadowing collisions during the renaming phase.
- **Smart Alias Injection**: A cost-benefit algorithm evaluates the frequency of deep API calls (e.g., `screen.drawRectF`) and dynamically hoists them into 1-character root-level aliases (e.g., `local A=screen.drawRectF`) if the byte overhead yields a net size reduction.
- **Deduplication Pass**: Recursively identifies heavily utilized string and numeric literals and converts them into referenced constants to eliminate redundant payload bytes.
- **Dead Code Elimination (DCE)**: Prunes unreferenced imports, unused functions, and redundant locals by checking reference counts on the final pass.
- **Slot-Allocator Renaming**: Reallocates variable identifiers across peer-level scopes using a sorted, greedy algorithm. The most frequently accessed variables are assigned the shortest possible lexicographic names (`a`, `b`, `c`), reusing identifier slots when scopes do not overlap.

## Integrated Tooling

### Obfuscator Engine
The obfuscation module applies aggressive name mangling to all symbol tables and performs symmetric hex-encryption on string literals. A self-executing unpacker is injected at the top of the bundle, reconstructing string tables dynamically in memory at runtime to prevent static reverse-engineering.

### Sprite Vectorizer (Hex Engine)
A high-density packing utility that compiles raster image data into highly optimized Lua draw commands. 
- Employs 8-character hex data packing.
- Uses binary-search constraint fitting to dial the output to exactly the 8,192-character limit, extracting maximum possible resolution without engine rejection.
- Automatically handles color quantization (64, 32, 16 palettes) and implements dynamic `getWidth()` centering logic for hardware-agnostic rendering.

### XML Auto-Deployer
An integrated deployment daemon that natively parses Stormworks `microprocessors/*.xml` files. When a script modification is detected in the workspace, it bypasses the clipboard entirely, traversing the XML DOM to directly inject the compiled minified payload into the corresponding `<object script="..."/>` tags. Supports multi-node logic via prefix routing (e.g., `1_EngineControl.lua`).

## Usage & Build Instructions

The application provides a sleek CustomTkinter graphical interface.

**Requirements:**
- Python 3.10+
- Dependencies listed in `requirements.txt`

**Build:**
Run `build.bat` in a Windows environment. The script utilizes PyInstaller to compile the source pipeline and dependencies into a standalone executable. The output distributable will be written to `_export/VladgeMinifier/`.

---
*Proprietary toolset. See LICENSE for usage terms.*
