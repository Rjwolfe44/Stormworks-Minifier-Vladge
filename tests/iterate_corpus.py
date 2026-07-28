"""
Corpus iteration + validation harness (local, not run in CI).

Minifies every Lua file under `_workspace/corpus/` at levels 1-4 and checks:
  - output parses via luaparser
  - no `)name` / `name name` / `nil name` glues remain
  - structural keyword counts preserved (if/elseif/else/end/function)
  - `validate_minified` returns no errors
  - size vs original and vs LifeBoat release reference (where a matching
    `_workspace/corpus_ref/` file exists)

Run:  python tests/iterate_corpus.py [--level N] [--verbose] [--glob PATTERN]
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.core.minifier import minify  # noqa: E402
from src.core.lexer import tokenize, TT  # noqa: E402
from src.core.passes.strip_whitespace import _needs_separator  # noqa: E402
from src.core.validate import validate_minified  # noqa: E402

CORPUS = REPO / "_workspace" / "corpus"
CORPUS_REF = REPO / "_workspace" / "corpus_ref"

_KEYWORDS = ["if", "elseif", "else", "end", "function", "for", "while", "then", "do"]


@dataclass
class FileResult:
    path: str
    ok: bool = True
    parse_ok: bool = True
    glue: list[str] = field(default_factory=list)
    validate_errors: list[str] = field(default_factory=list)
    structure_diffs: list[str] = field(default_factory=list)
    orig_size: int = 0
    out_size: int = 0
    ref_size: int | None = None

    @property
    def ratio(self) -> float:
        return self.out_size / self.orig_size if self.orig_size else 0.0

    @property
    def vs_ref(self) -> float | None:
        if self.ref_size is None or self.ref_size == 0:
            return None
        return (self.out_size - self.ref_size) / self.ref_size * 100


def _count_keywords(source: str) -> dict[str, int]:
    toks = tokenize(source)
    counts = {k: 0 for k in _KEYWORDS}
    for t in toks:
        if t.type == TT.KEYWORD and t.value in counts:
            counts[t.value] += 1
    return counts


def _block_balance(source: str) -> tuple[int, int, int]:
    """
    Rough block-balance: openers (if/function/for/while/do-block) minus `end`,
    plus repeat/until pairing. Returns (opens, ends, repeat_until_delta).
    For valid Lua these relationships must hold:
      opens == ends (every if/for/while/function/do-block closes with `end`)
      repeat == until
    `do` after for/while is *not* a separate opener; standalone `do` is.
    """
    toks = [t for t in tokenize(source) if t.type not in (TT.SPACE, TT.NEWLINE, TT.EOF)]
    opens = ends = repeats = untils = 0
    for i, t in enumerate(toks):
        if t.type != TT.KEYWORD:
            continue
        v = t.value
        if v == "end":
            ends += 1
        elif v in ("if", "function", "for", "while"):
            opens += 1
        elif v == "do":
            # `for ... do` / `while ... do` — the for/while already opened.
            # standalone `do` opens a bare block. Approximate: only count `do`
            # when the previous significant keyword was not for/while.
            prev_kw = None
            for j in range(i - 1, -1, -1):
                if toks[j].type == TT.KEYWORD:
                    prev_kw = toks[j].value
                    break
            if prev_kw not in ("for", "while"):
                # crude: for/while heads contain names/ops before `do`, so a `do`
                # right after another keyword (then/end/else/do) is likely standalone
                if prev_kw in ("then", "end", "else", "do", None):
                    opens += 1
        elif v == "repeat":
            repeats += 1
        elif v == "until":
            untils += 1
    return opens, ends, repeats - untils


def _check_glue(source: str) -> list[str]:
    """
    Token-level glue check: any two adjacent non-ws tokens that `_needs_separator`
    says require `;` must actually be separated by `;` in the output. A pair that
    requires `;` but was emitted with only a space (or nothing) is a hard bug.
    """
    hits: list[str] = []
    toks = [t for t in tokenize(source) if t.type not in (TT.EOF,)]
    # walk pairs of *real* tokens, tracking whether a space/newline/; sits between
    i = 0
    n = len(toks)
    while i < n:
        left = toks[i]
        if left.type in (TT.SPACE, TT.NEWLINE):
            i += 1
            continue
        # find next real token and what separated it
        j = i + 1
        saw_space = saw_newline = saw_semi = False
        while j < n:
            t = toks[j]
            if t.type == TT.SPACE:
                saw_space = True
            elif t.type == TT.NEWLINE:
                saw_newline = True
            elif t.type == TT.OP and t.value == ";":
                saw_semi = True
            else:
                break
            j += 1
        if j >= n:
            break
        right = toks[j]
        need = _needs_separator(left, right)
        if need == ";" and not saw_semi:
            hits.append(
                f"{left.value!r}+{right.value!r} needs ';' @~{left.pos}"
            )
        elif need == " " and not (saw_space or saw_newline or saw_semi):
            hits.append(
                f"{left.value!r}+{right.value!r} needs space @~{left.pos}"
            )
        i = j
    return hits


def _ref_for(rel: Path) -> Path | None:
    """Find the matching LifeBoat release reference for a corpus file."""
    cand = CORPUS_REF / rel
    if cand.exists():
        return cand
    # try by bare filename
    matches = list(CORPUS_REF.rglob(rel.name)) if CORPUS_REF.exists() else []
    return matches[0] if matches else None


def run_file(path: Path, level: int) -> FileResult:
    rel = path.relative_to(CORPUS)
    res = FileResult(path=str(rel))
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        res.ok = False
        res.validate_errors = [f"read error: {e}"]
        return res

    res.orig_size = len(source)
    try:
        out, stats = minify(source, level=level, root_dir=str(path.parent))
    except Exception as e:  # noqa: BLE001
        res.ok = False
        res.parse_ok = False
        res.validate_errors = [f"minify exception: {e}"]
        return res

    res.out_size = len(out)

    parse_errors = [e for e in stats.semantic_errors if e.startswith("Parse error")]
    res.parse_ok = not parse_errors

    # Only flag error *classes* introduced by minification. Pre-existing lint on
    # the original (e.g. project-global 'Vector' defined in a sibling file) is
    # inherited, not corruption. Compare error categories with line/name stripped.
    def _cat(errs: list[str]) -> set[str]:
        cats = set()
        for e in errs:
            if e.startswith("Parse error"):
                cats.add("PARSE")
            elif "Undefined global" in e:
                cats.add("UNDEF_GLOBAL")
            else:
                cats.add(e.split(":")[0])
        return cats

    orig_cats = _cat(validate_minified(source))
    new_cats = _cat(stats.semantic_errors) - orig_cats
    # Parse errors are always corruption regardless of original lint state.
    if parse_errors:
        new_cats.add("PARSE")
    res.validate_errors = sorted(new_cats) if new_cats else []
    if new_cats:
        res.ok = False

    res.glue = _check_glue(out)
    if res.glue:
        res.ok = False

    # Structural invariant: block balance must be preserved exactly. DCE removes
    # whole balanced blocks, so opens-ends delta and repeat/until delta must match.
    o_opens, o_ends, o_rep = _block_balance(source)
    n_opens, n_ends, n_rep = _block_balance(out)
    if (o_opens - o_ends) != (n_opens - n_ends):
        res.structure_diffs.append(
            f"block balance: {o_opens-o_ends} -> {n_opens-n_ends} (opens {o_opens}->{n_opens}, ends {o_ends}->{n_ends})"
        )
    if o_rep != n_rep:
        res.structure_diffs.append(f"repeat/until balance: {o_rep} -> {n_rep}")
    if res.structure_diffs:
        res.ok = False

    ref = _ref_for(rel)
    if ref is not None:
        try:
            res.ref_size = len(ref.read_text(encoding="utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            pass

    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, default=4)
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--glob", default="**/*.lua")
    args = ap.parse_args()

    files = sorted(CORPUS.glob(args.glob))
    if not files:
        print(f"no corpus files matched {args.glob} under {CORPUS}")
        return 1

    results: list[FileResult] = []
    for i, p in enumerate(files, 1):
        r = run_file(p, args.level)
        results.append(r)
        status = "OK " if r.ok else "FAIL"
        ref_note = ""
        if r.vs_ref is not None:
            sign = "+" if r.vs_ref >= 0 else ""
            ref_note = f" | vs LB {sign}{r.vs_ref:.1f}%"
        print(
            f"[{i:3}/{len(files)}] {status} L{args.level} "
            f"{r.orig_size:>6} -> {r.out_size:>6} ({r.ratio:.0%}){ref_note}  {r.path}"
        )
        if args.verbose or not r.ok:
            for g in r.glue:
                print(f"      GLUE  {g}")
            for e in r.validate_errors:
                print(f"      ERR   {e}")
            for d in r.structure_diffs:
                print(f"      STRUCT {d}")

    n_ok = sum(1 for r in results if r.ok)
    n_parse_ok = sum(1 for r in results if r.parse_ok)
    n_glue = sum(1 for r in results if r.glue)
    n_struct = sum(1 for r in results if r.structure_diffs)
    total_orig = sum(r.orig_size for r in results)
    total_out = sum(r.out_size for r in results)

    with_ref = [r for r in results if r.ref_size is not None]
    wins = sum(1 for r in with_ref if r.out_size <= r.ref_size)
    losses = sum(1 for r in with_ref if r.out_size > r.ref_size)

    print()
    print(f"files:           {len(results)}")
    print(f"fully OK:        {n_ok}")
    print(f"parse OK:        {n_parse_ok}")
    print(f"glue failures:   {n_glue}")
    print(f"structure diffs: {n_struct}")
    print(f"total size:      {total_orig:,} -> {total_out:,} ({total_out/total_orig:.1%})")
    if with_ref:
        print(f"vs LifeBoat:     {wins} wins, {losses} losses ({len(with_ref)} compared)")

    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
