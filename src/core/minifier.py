"""
VladgeMinifier - Core Minification Orchestrator
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Union

from .lexer import tokenize, tokens_to_source, Token
from .passes.strip_comments import strip_comments
from .passes.strip_whitespace import strip_whitespace, MultilineMode
from .passes.rename_locals import rename_locals
from .passes.alias_globals import inject_global_aliases
from .passes.number_literals import optimise_numbers
from .passes.string_dedup import dedup_strings
from .addon_mode import ADDON_CHAR_LIMIT, MC_CHAR_LIMIT, finalize_addon_source

CHAR_LIMIT = MC_CHAR_LIMIT  # default microcontroller ceiling; overridden per-run via stats.char_limit


def _resolve_multiline(multiline: Union[bool, str]) -> MultilineMode:
    if multiline is True:
        return "statements"
    if multiline is False or multiline == "off":
        return "singleline"
    if multiline in ("singleline", "statements", "preserve"):
        return multiline  # type: ignore[return-value]
    return "singleline"


@dataclass
class MinifyStats:
    """Detailed statistics from a minification run."""
    original_size: int = 0
    final_size: int = 0
    elapsed_ms: float = 0.0
    char_limit: int = MC_CHAR_LIMIT
    mode: str = "microcontroller"  # or "addon"

    comments_removed: int = 0
    whitespace_saved: int = 0
    sections_stripped: int = 0
    dead_locals: int = 0
    dead_globals: int = 0
    dead_funcs: int = 0
    zipped_locals: int = 0
    literals_deduped: int = 0
    vars_renamed: int = 0
    globals_renamed: int = 0
    global_renames_map: Dict[str, str] = field(default_factory=dict)
    globals_aliased: int = 0
    globals_alias_map: Dict[str, str] = field(default_factory=dict)
    numbers_optimised: int = 0
    strings_deduped: int = 0
    constants_inlined: int = 0
    constants_inlined_late: int = 0
    functions_inlined: int = 0
    property_packed: int = 0
    ast_dce_parse_error: str | None = None

    rename_map: Dict[str, str] = field(default_factory=dict)

    level: int = 3
    level_name: str = "Aggressive"
    semantic_errors: List[str] = field(default_factory=list)

    @property
    def bytes_saved(self) -> int:
        return self.original_size - self.final_size

    @property
    def ratio(self) -> float:
        if self.original_size == 0:
            return 0.0
        return (self.bytes_saved / self.original_size) * 100

    @property
    def under_limit(self) -> bool:
        return self.final_size <= self.char_limit

    @property
    def semantic_ok(self) -> bool:
        return not self.semantic_errors

    @property
    def limit_pct(self) -> float:
        return (self.final_size / self.char_limit) * 100 if self.char_limit else 0.0

    def summary_lines(self) -> List[str]:
        lines = [
            f"* Comments removed:        {self.comments_removed}",
            f"* Whitespace saved:        {self.whitespace_saved:,} chars",
        ]
        if self.vars_renamed:
            lines.append(f"* Local vars renamed:      {self.vars_renamed}")
        if self.zipped_locals:
            lines.append(f"* Local decls zipped:      {self.zipped_locals}")
        if self.literals_deduped:
            lines.append(f"* Literals deduplicated:   Saved {self.literals_deduped} chars")
        if self.globals_renamed:
            lines.append(f"* Globals renamed:         {self.globals_renamed}")
        if self.sections_stripped:
            lines.append(f"* Sections stripped:       {self.sections_stripped}")
        if self.dead_locals or self.dead_globals or self.dead_funcs:
            lines.append(
                f"* Dead code eliminated:    {self.dead_locals} locals, "
                f"{self.dead_globals} globals, {self.dead_funcs} funcs"
            )
        if self.constants_inlined or self.constants_inlined_late:
            lines.append(
                f"* Constants inlined:       {self.constants_inlined} early, "
                f"{self.constants_inlined_late} late"
            )
        if self.functions_inlined:
            lines.append(f"* Functions inlined:       {self.functions_inlined}")
        if self.property_packed:
            lines.append(f"* Property strings packed: {self.property_packed} chars")
        if self.globals_aliased:
            lines.append(f"* SW APIs macro-aliased:   {self.globals_aliased}")
        if self.numbers_optimised:
            lines.append(f"* Number literals fixed:   {self.numbers_optimised}")
        if self.strings_deduped:
            lines.append(f"* Strings deduplicated:    {self.strings_deduped}")
        if self.ast_dce_parse_error:
            lines.append(f"* AST DCE parse skipped:   {self.ast_dce_parse_error[:60]}")
        return lines


LEVEL_NAMES = {
    1: "Strip Only",
    2: "Standard",
    3: "Aggressive",
    4: "Ultimate",
}


def minify(
    source: str,
    level: int = 3,
    root_dir: str = None,
    obfuscate: bool = False,
    drop_locals: bool = False,
    multiline: Union[bool, str] = False,
    inline_functions: bool = False,
    lua53_floor: bool = False,
    addon: bool = False,
) -> tuple[str, MinifyStats]:
    """Minify Lua source at the given optimisation level.

    addon=True: mission/addon script mode (131071 char limit, property.* line breaks,
    skip property-string packing that targets microcontroller PINs).
    """
    t0 = time.perf_counter()
    # Addon mission UI + debugging: prefer statement breaks when caller left default off.
    if addon and (multiline is False or multiline == "off"):
        multiline = "statements"
    ws_mode = _resolve_multiline(multiline)
    stats = MinifyStats(
        original_size=len(source),
        level=level,
        level_name=LEVEL_NAMES.get(level, "Unknown"),
        char_limit=ADDON_CHAR_LIMIT if addon else MC_CHAR_LIMIT,
        mode="addon" if addon else "microcontroller",
    )

    source = source.replace("\r\n", "\n").replace("\r", "\n")

    # Stormworks MC/addon Lua has no pcall — unwrap before any other pass.
    from .passes.sw_runtime import unwrap_pcall
    source, _pcall_unwrapped = unwrap_pcall(source)

    l3_fallback: tuple[str, MinifyStats] | None = None
    if level == 4:
        l3_fallback = minify(
            source,
            level=3,
            root_dir=root_dir,
            obfuscate=obfuscate,
            drop_locals=drop_locals,
            multiline=multiline,
            inline_functions=False,
            lua53_floor=lua53_floor,
            addon=addon,
        )

    from .passes.combiner import bundle_requires
    source = bundle_requires(source, root_dir)

    from .passes.section_stripper import strip_dead_sections
    source, stats.sections_stripped = strip_dead_sections(source)

    # Level 3+ structure packing (source-level, pre-tokenize)
    if level >= 3:
        from .passes.default_pack import compress_default_chains
        source, _ = compress_default_chains(source)
        # property_pack targets microcontroller property.getNumber PIN strings — skip for addons
        if not addon:
            from .passes.property_pack import pack_property_strings
            source, packed = pack_property_strings(source)
            stats.property_packed += packed

    if level >= 4:
        from .passes.vector_pack import pack_vector_tables
        source, _ = pack_vector_tables(source)

    if level >= 4:
        from .passes.ast_dce import ast_eliminate_dead_code
        source, stats.dead_funcs, stats.ast_dce_parse_error = ast_eliminate_dead_code(source)

    tokens: List[Token] = tokenize(source)

    if level >= 4:
        from .passes.constant_inliner import inline_constants
        tokens, early = inline_constants(tokens)
        stats.constants_inlined = early

    if obfuscate:
        from .passes.obfuscate_strings import obfuscate_strings
        tokens, stats.strings_deduped = obfuscate_strings(tokens)

    if level >= 4 and not obfuscate:
        from .passes.token_optimizer import optimize_tokens
        tokens, stats.vars_renamed = optimize_tokens(tokens, lua53_floor=lua53_floor)

    tokens, stats.comments_removed = strip_comments(tokens)
    tokens, stats.numbers_optimised = optimise_numbers(tokens)

    if level >= 4:
        from .passes.constant_folder import fold_constants
        tokens, folded = fold_constants(tokens)
        stats.numbers_optimised += folded

    # Late constant inliner (after fold, before token DCE)
    if level >= 4:
        from .passes.constant_inliner import inline_constants
        tokens, late = inline_constants(tokens)
        stats.constants_inlined_late = late

    if level >= 4:
        from .passes.dce import eliminate_dead_code
        tokens, stats.dead_locals, stats.dead_globals = eliminate_dead_code(tokens)

    # Auto selective inlining at L4 (single-use, net savings); --inline-functions allows 3 sites
    if level >= 4:
        from .passes.inline_functions import inline_functions as do_inline_functions
        max_sites = 3 if inline_functions else 1
        tokens, n_inline = do_inline_functions(
            tokens, max_call_sites=max_sites, require_net_savings=True,
        )
        stats.functions_inlined += n_inline
        if n_inline:
            from .passes.dce import eliminate_dead_code
            tokens, dl, dg = eliminate_dead_code(tokens)
            stats.dead_locals += dl
            stats.dead_globals += dg

    if level >= 4:
        from .passes.zipper import consolidate_locals
        tokens, stats.zipped_locals = consolidate_locals(tokens)

    if level >= 4:
        from .passes.ternary_injector import inject_ternary
        from .passes.short_circuit import inject_short_circuit
        tokens, ternary_count = inject_ternary(tokens)
        tokens, short_circuit_count = inject_short_circuit(tokens)
        stats.comments_removed += ternary_count + short_circuit_count

    allocated_globals = set()

    if level >= 3:
        from .passes.rename_globals import rename_globals
        tokens, stats.globals_renamed, stats.global_renames_map, allocated_globals = rename_globals(
            tokens, allocated_globals, obfuscate
        )

    if level >= 4 and not obfuscate:
        from .passes.literal_dedup import dedup_literals
        before_lit = tokens_to_source(tokens)
        cand_tokens, lit_saved = dedup_literals(tokens, allocated_globals)
        if len(tokens_to_source(cand_tokens)) < len(before_lit):
            tokens = cand_tokens
            stats.literals_deduped = lit_saved

    if level >= 2:
        tokens, stats.vars_renamed, stats.rename_map = rename_locals(
            tokens, reserved_names=allocated_globals, obfuscate=obfuscate
        )

    if drop_locals:
        from .passes.drop_locals import drop_global_locals
        tokens, dropped_saved = drop_global_locals(tokens)
        stats.comments_removed += dropped_saved

    tokens, ws_saved = strip_whitespace(tokens, mode=ws_mode)
    stats.whitespace_saved += ws_saved

    current_source = tokens_to_source(tokens)

    if level >= 3 and not addon:
        from .passes.property_pack import pack_property_strings
        current_source, late_pack = pack_property_strings(current_source)
        stats.property_packed += late_pack

    if level == 4:
        from .passes.smart_alias import smart_alias_globals
        before_alias = current_source
        current_source, _, stats.globals_alias_map = smart_alias_globals(current_source)
        if len(current_source) > len(before_alias):
            current_source, _, stats.globals_alias_map = inject_global_aliases(before_alias)
        stats.globals_aliased = len(stats.globals_alias_map)
    elif level >= 3:
        current_source, _, stats.globals_alias_map = inject_global_aliases(current_source)
        stats.globals_aliased = len(stats.globals_alias_map)

    # Re-strip after alias injection so `)input` → `)_a` cannot glue illegally.
    if level >= 3 and stats.globals_aliased:
        tokens_alias = tokenize(current_source)
        tokens_alias, alias_ws = strip_whitespace(tokens_alias, mode=ws_mode)
        current_source = tokens_to_source(tokens_alias)
        stats.whitespace_saved += alias_ws

    if level >= 4 and not obfuscate:
        tokens2 = tokenize(current_source)
        before_dedup = current_source
        tokens2, dedup_saved, str_map = dedup_strings(tokens2)
        candidate = tokens_to_source(strip_whitespace(tokens2, mode=ws_mode)[0])
        if len(candidate) < len(before_dedup):
            stats.strings_deduped = len(str_map)
            current_source = candidate
        else:
            tokens2 = tokenize(before_dedup)

        # Peephole re-pass — only keep if smaller
        before_peep = current_source
        tokens2 = tokenize(before_peep)
        tokens2, extra_nums = optimise_numbers(tokens2)
        tokens2, extra_ws = strip_whitespace(tokens2, mode=ws_mode)
        candidate = tokens_to_source(tokens2)
        if len(candidate) < len(before_peep):
            stats.numbers_optimised += extra_nums
            stats.whitespace_saved += extra_ws
            current_source = candidate

    if level == 4 and l3_fallback is not None:
        l3_out, l3_stats = l3_fallback
        if len(current_source) > len(l3_out):
            current_source = l3_out
            stats.final_size = l3_stats.final_size
            stats.char_limit = l3_stats.char_limit
            stats.mode = l3_stats.mode
            stats.semantic_errors = l3_stats.semantic_errors
            stats.elapsed_ms = (time.perf_counter() - t0) * 1000
            if addon:
                current_source = finalize_addon_source(current_source)
                stats.final_size = len(current_source)
            return current_source, stats

    if addon:
        current_source = finalize_addon_source(current_source)

    stats.final_size = len(current_source)
    stats.elapsed_ms = (time.perf_counter() - t0) * 1000

    from .validate import validate_minified
    stats.semantic_errors = validate_minified(current_source)

    return current_source, stats


def minify_file(
    path: str,
    level: int = 3,
    obfuscate: bool = False,
    drop_locals: bool = False,
    multiline: Union[bool, str] = False,
    inline_functions: bool = False,
    lua53_floor: bool = False,
    addon: bool = False,
) -> tuple[str, MinifyStats]:
    import os
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        source = f.read()
    root_dir = os.path.dirname(os.path.abspath(path))
    return minify(
        source,
        level,
        root_dir=root_dir,
        obfuscate=obfuscate,
        drop_locals=drop_locals,
        multiline=multiline,
        inline_functions=inline_functions,
        lua53_floor=lua53_floor,
        addon=addon,
    )
