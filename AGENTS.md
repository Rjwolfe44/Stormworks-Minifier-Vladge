# Agent guide — VladgeMinifier

Stormworks Lua minifier/obfuscator (GUI + CLI). Target: microcontroller **8192** char limit. Repo: [Rjwolfe44/Stormworks-Minifier-Vladge](https://github.com/Rjwolfe44/Stormworks-Minifier-Vladge).

Read this before changing the pipeline, releasing, or committing.

---

## Critical: Cursor git interception

Cursor’s agent shell **intercepts** `git commit` / `git commit-tree` and injects:

```text
Co-authored-by: Cursor <cursoragent@cursor.com>
```

That makes **cursoragent** show up as a GitHub contributor. Do **not** use plain `git commit` from the agent shell for this repo.

### Bypass (required for clean commits)

Call Git’s real binary via **Python** (PowerShell `git` / `git.exe` under `cmd` may still be wrapped):

```python
import subprocess, os
from pathlib import Path

GIT = r"C:\Program Files\Git\mingw64\bin\git.exe"

def run(args, **kw):
    return subprocess.run([GIT, *args], check=True, text=True, **kw)

# Stage
run(["add", "-A", "--", "src", "tests", "src/version.py"])  # be selective; never add test_out*.lua

# Commit without Cursor trailer
msg = Path(".git/AMEND_MSG.txt")
msg.write_text(
    "your subject\n\nbody here.\n",
    encoding="utf-8",
    newline="\n",
)
env = os.environ.copy()
# Optional: preserve author from last commit
# env["GIT_AUTHOR_NAME"] = ...
run(["commit", "-F", str(msg)], env=env)

# Verify no trailer
body = subprocess.check_output([GIT, "log", "-1", "--format=%B"], text=True)
assert "Co-authored-by: Cursor" not in body
```

### Rewrite a commit that already has the trailer

If HEAD was already pushed with the trailer:

1. Rebuild the same tree with `commit-tree` via the **mingw64** `git.exe` + Python (same as above).
2. `git reset --hard <newsha>`
3. `git push --force-with-lease origin main` (only with explicit user OK for force-push to main).
4. Move the release tag: `git tag -d vX.Y.Z && git tag vX.Y.Z && git push --force origin vX.Y.Z`

GitHub’s **Contributors** sidebar can stay stale for hours/days after removing dangling commits; the commits API is the source of truth.

### Do not commit

- `_workspace/` (old agent memory dumps)
- `test_out.lua`, `test_out2.lua`, `test_out3.lua`, `debug.txt`
- `dist/`, `build/`, `_export/`

---

## Where everything lives

| Path | Role |
|------|------|
| [`src/version.py`](src/version.py) | **Single version string** (`__version__`). Bump here for releases. |
| [`src/core/minifier.py`](src/core/minifier.py) | Pipeline orchestrator (levels 1–4), `MinifyStats`, hooks semantic validation |
| [`src/core/lexer.py`](src/core/lexer.py) | Tokenizer; `SW_GLOBALS`, `SW_API_PROPERTIES` allowlists |
| [`src/core/scope.py`](src/core/scope.py) | `build_scope_tree` — **for + nested while `do` uses one-shot `pending_for_do`** |
| [`src/core/renamer.py`](src/core/renamer.py) | Short-name allocator for locals |
| [`src/core/validate.py`](src/core/validate.py) | Post-minify **parse** (luaparser) + semantic check |
| [`src/core/linter.py`](src/core/linter.py) | Pre-minify / shared undefined-global lint |
| [`src/core/linter_shortcircuit.py`](src/core/linter_shortcircuit.py) | Dead-branch / safe nil-read helpers for linter |
| [`src/core/passes/`](src/core/passes/) | All transform passes (rename, alias, DCE, golf, etc.) |
| [`src/core/passes/rename_locals.py`](src/core/passes/rename_locals.py) | Local rename; list-valued scope start/end indexes |
| [`src/core/passes/rename_globals.py`](src/core/passes/rename_globals.py) | Standalone globals + **user** table keys/props; **never** rename SW API props |
| [`src/core/passes/token_optimizer.py`](src/core/passes/token_optimizer.py) | L4 golf; **`math.floor` → `//1` is disabled** |
| [`src/cli/main.py`](src/cli/main.py) | CLI; prints `[OK]` / `[BROKEN]` / over-limit; exit 2 on semantic errors |
| [`src/gui/app.py`](src/gui/app.py) | CustomTkinter GUI + status badge |
| [`src/gui/sprite_converter.py`](src/gui/sprite_converter.py) | Image → Lua draw packing |
| [`src/core/deployer.py`](src/core/deployer.py) | XML microcontroller inject |
| [`tests/`](tests/) | pytest; Lifeboat compare needs local Code Folder path |
| [`tests/test_semantic_corruption.py`](tests/test_semantic_corruption.py) | while-sort, map API, floor, validator regressions |
| [`build.bat`](build.bat) | Local PyInstaller build → `_export/VladgeMinifier/` |
| [`build.spec`](build.spec) | PyInstaller spec (GUI + CLI + standalone) |
| [`publish.py`](publish.py) | Local: pytest → build → zip → `gh release` (optional; CI also releases on tags) |
| [`.github/workflows/build-and-release.yml`](.github/workflows/build-and-release.yml) | On `v*` tag: test, build, upload zip + standalone exe |
| [`README.md`](README.md) | User-facing product description |

Scratch / do-not-trust-as-source-of-truth: `_workspace/docs/` (old chat dumps). Prefer this file + code.

---

## Minify levels (quick)

| Level | Name | Main extras |
|-------|------|-------------|
| 1 | Strip Only | comments, whitespace, number literals |
| 2 | Standard | + rename locals |
| 3 | Aggressive (default) | + rename globals/user props, API aliases |
| 4 | Ultimate | + AST DCE, constant inline (early/late), token DCE, **auto selective inline** (net savings), property pack, literal/string dedup, smart alias, peephole; **monotonic** late passes; **L3 fallback** if L4 grows |

### L4 pass order (2.3.2)

`bundle` → `section_strip` → `default_pack` → **`property_pack` (early)** → `vector_pack` → `ast_dce` → tokenize → early `constant_inliner` → `token_optimizer` → strip/numbers → `constant_folder` → late `constant_inliner` → token `dce` → **auto `inline_functions`** (1 site; 3 with `--inline-functions`; net savings) → zipper/ternary → rename → **monotonic `literal_dedup`** → strip → **`property_pack` (late)** → alias (**smart_alias** with inject fallback) → **monotonic** string dedup → peephole → **if L4 > L3 size: revert to L3 output** → **validate**

### CLI / GUI flags (2.3.0+)

| Flag | CLI | GUI | Default |
|------|-----|-----|---------|
| Multiline | `--multiline off\|statements\|preserve` | **Keep line breaks** (`statements`) | off (single line) |
| Inline functions | `--inline-functions` | **Inline funcs** | off (L4 still auto-inlines 1-site net-positive funcs) |
| Lua 5.3 floor | `--lua53-floor` | — | off (`math.floor` → `(x)//1` opt-in) |

### Verification layers

| Layer | Where | On fail |
|-------|--------|---------|
| Parse | `validate.py` → `luaparser.ast.parse` | `[BROKEN]` / pytest |
| Semantic | `validate.py` → `lint_script` + SW prop check | `[BROKEN]` / exit 2 |
| Linter | `linter_shortcircuit.py` + unreachable-func suppression | fewer false positives (dead branches, dead libs) |
| Corpus | `tests/test_corpus_verify.py` (skipif no Code Folder) | L2/L4 parse + semantic |
| Helpers | `tests/helpers_verify.py` | shared by tests |

**Not automatable:** full Stormworks physics/API runtime. In-game paste is still the final gate.

### Manual spot-check (each release)

Paste minified L4 output in Stormworks microcontroller, confirm `onTick` runs:

1. Car Guidance
2. Datalink V2
3. AirVehicleMover (if present)
4. Steering Wheel Controller

Also test **Keep line breaks** on/off for Car Guidance + Datalink V2.

### Lifeboat baseline refresh

Fair compare in `tests/test_vs_lifeboat.py` uses cached Lifeboat output under `_build/out/release/`. Re-minify current Code Folder scripts with Lifeboat locally and copy into that folder when refreshing the baseline.

Stormworks callbacks (`onTick`, `onDraw`, …) and API tables (`screen`, `map`, `math`, …) must never be renamed. Property names after those tables must stay (`map.mapToScreen`, not `map.a`).

User structs **do** minify at L3+: `{ yaw = 1 }` / `obj.yaw` rename together by shared identifier string. SW receivers are default-deny.

---

## Hard-won bug rules (do not regress)

1. **`for` + nested `while … do`**: `pending_for_do` must be one-shot. Never skip every `do` while `current` is still the for-scope — that closes the for at the while’s `end` and leaves post-while locals unrenamed (`a[j+1]=k`, `for a=1,nH`).
2. **SW API properties**: incomplete allowlist + renaming `.`/`:` on `map`/`screen` causes nil-field crashes. Keep allowlist updated; keep default-deny on `SW_GLOBALS` receivers.
3. **`len` / API-named table keys**: protect keys in `SW_API_PROPERTIES` so `{ len = … }` matches `:len()`.
4. **Size `[OK]` ≠ semantic OK**: always run `validate_minified`; CLI/GUI must surface `[BROKEN]`.
5. **`math.floor` → `//1`**: disabled by default; enable only with `--lua53-floor` / `lua53_floor=True` and in-game test.
6. **Token DCE**: removes unused **local** decls only; global orphan removal is unsafe pre-rename — do not re-enable without constant-inliner markers.
7. **Structure packs** (`default_pack`, `vector_pack`): must pass luaparser on candidate output before applying.
8. **L4 monotonic**: string dedup, literal dedup, peephole, smart alias must not grow output; L4 falls back to L3 if final size is larger.
9. **Linter short-circuit**: undefined reads in dead `and` branches and falsy `or` chains are not flagged; reads inside global funcs unreachable from `onTick`/`onDraw`/… are skipped.
10. **Constant inline before `:`, `.`, `[`**: bare string/number/`nil`/`true`/`false` literals are not Lua prefixexps. Inlining `s:sub(...)` must emit `("hello"):sub(...)`, never `"hello":sub(...)`.

Regression fixtures live in `tests/test_semantic_corruption.py`, `tests/test_linter_shortcircuit.py`.

---

## Build / release workflow

1. Bump [`src/version.py`](src/version.py).
2. Run full tests: `python -m pytest tests/ -q`
3. Commit with the **Python + mingw64 git bypass** (no Cursor trailer).
4. `git push origin main`
5. Tag and push: `git tag vX.Y.Z` then `git push origin vX.Y.Z`  
   → GitHub Actions builds and publishes the release.
6. Optional local: `.\build.bat` → `_export\VladgeMinifier\` (GUI + CLI). Or `python publish.py`.

Releases: zip only (folder with GUI + CLI). Autoupdater downloads the zip, extracts flat or nested `VladgeMinifier/`, and overwrites the install dir — don’t regress that. Standalone onefile exe was removed in 2.3.3+.

Lifeboat benchmark: `tests/test_vs_lifeboat.py` points at a local Proton Drive Code Folder; CI may skip if missing. Overall Vladge L4 should stay ahead of Lifeboat on aggregate; `Car Guidance.lua` is a known Lifeboat DCE outlier.

---

## User / product context

- Competing with LifeboatAPI minifier for Stormworks scripts.
- Real scripts often use `require()` libs (vectors, etc.) — combiner + tree shaking matter.
- Prefer concise, accurate agent replies; don’t claim a fix is shipped until version bump + tag/CI (or local build) actually happened.
