"""
VladgeMinifier CLI - Command-line interface for VS Code / Cursor tasks.

Usage:
  vladgeminifier <file> [options]
  vladgeminifier <folder> --batch [options]

Options:
  --level {1,2,3,4}     Minification level (default: 3)
  --clipboard           Copy result to clipboard
  --no-save             Do not write an output file (use with --clipboard)
  --save <path>         Save output to file (default: _minified/<filename>)
  --deploy <dir>        Deploy the output file(s) into the specified directory
  --batch               Process all .lua files in a folder
  --workers <n>         Number of parallel workers for batch (default: auto)
  --quiet               Suppress stats output
"""

from __future__ import annotations
import argparse
import os
import sys
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

# Add project root to path when running as script
_HERE = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_HERE))

from src.core.minifier import minify, minify_file, CHAR_LIMIT, LEVEL_NAMES
from src.version import __version__


# ANSI colours (Windows 10+ supports them)
RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
DIM    = "\033[2m"


def _color_bar(pct: float, width: int = 30) -> str:
    filled = int(width * pct / 100)
    color = GREEN if pct < 70 else YELLOW if pct < 90 else RED
    bar = "#" * filled + "-" * (width - filled)
    return f"{color}[{bar}]{RESET} {pct:.1f}%"


def print_stats(stats, filename: str = ""):
    if filename:
        print(f"\n{BOLD}{CYAN}=== VladgeMinifier: {filename} ==={RESET}")
    print(f"  Level:     {BOLD}{stats.level} - {stats.level_name}{RESET}")
    print(f"  Before:    {stats.original_size:,} chars")
    print(f"  After:     {BOLD}{stats.final_size:,}{RESET} chars  ({stats.ratio:.1f}% reduction)")
    print(f"  Saved:     {GREEN}{stats.bytes_saved:,}{RESET} chars  in {stats.elapsed_ms:.1f}ms")

    limit_pct = stats.limit_pct
    print(f"  8192 cap:  {_color_bar(limit_pct)}")

    if not stats.semantic_ok:
        n_err = len(stats.semantic_errors)
        print(f"  Status:    {RED}[BROKEN] {n_err} undefined/invalid ref(s){RESET}")
        for err in stats.semantic_errors[:8]:
            print(f"             {RED}{err}{RESET}")
        if n_err > 8:
            print(f"             {DIM}… and {n_err - 8} more{RESET}")
    elif stats.under_limit:
        print(f"  Status:    {GREEN}[OK] Under 8192 char limit{RESET}")
    else:
        over = stats.final_size - CHAR_LIMIT
        print(f"  Status:    {RED}[!!] Over limit by {over:,} chars!{RESET}")

    print()
    for line in stats.summary_lines():
        print(f"  {DIM}{line}{RESET}")
    print()


def _batch_worker(args):
    """Worker function for multicore batch processing."""
    path, level, obfuscate, multiline, inline_functions, lua53_floor = args
    try:
        result, stats = minify_file(
            str(path), level, obfuscate,
            multiline=multiline if multiline != "off" else False,
            inline_functions=inline_functions,
            lua53_floor=lua53_floor,
        )
        return path, result, stats, None
    except Exception as e:
        return path, None, None, str(e)


def process_single(input_path: Path, level: int, clipboard: bool, no_save: bool, save: str | None, deploy: str | None, quiet: bool, obfuscate: bool, multiline: str = "off", inline_functions: bool = False, lua53_floor: bool = False):
    """Process a single file."""
    result, stats = minify_file(
        str(input_path), level, obfuscate,
        multiline=multiline if multiline != "off" else False,
        inline_functions=inline_functions,
        lua53_floor=lua53_floor,
    )

    if not quiet:
        print_stats(stats, input_path.name)

    if not no_save:
        if save is None:
            out_dir = input_path.parent / "_minified"
            out_dir.mkdir(exist_ok=True)
            out_path = out_dir / input_path.name
        else:
            out_path = Path(save)
            out_path.parent.mkdir(parents=True, exist_ok=True)

        out_path.write_text(result, encoding="utf-8")
        if not quiet:
            print(f"  {GREEN}Saved -> {out_path}{RESET}\n")

    if deploy:
        deploy_dir = Path(deploy)
        from src.core.deployer import deploy_to_target
        is_xml = deploy_to_target(result, input_path.name, deploy_dir)
        if not quiet:
            if is_xml:
                print(f"  {GREEN}Injected -> XML Microcontroller in {deploy_dir}{RESET}\n")
            else:
                print(f"  {GREEN}Deployed -> {deploy_dir / input_path.name}{RESET}\n")

    if clipboard:
        try:
            import pyperclip
            pyperclip.copy(result)
            if not quiet:
                print(f"  {GREEN}[OK] Copied to clipboard!{RESET}\n")
        except ImportError:
            print(f"  {YELLOW}[!] pyperclip not installed - clipboard skipped{RESET}")
        except Exception as e:
            print(f"  {RED}Clipboard error: {e}{RESET}")

    if not stats.semantic_ok:
        sys.exit(2)

    return stats


def process_batch(folder: Path, level: int, workers: int, deploy: str | None, quiet: bool, obfuscate: bool, multiline: str = "off", inline_functions: bool = False, lua53_floor: bool = False):
    """Batch-process all .lua files in a folder (multicore)."""
    lua_files = list(folder.rglob("*.lua"))
    # Exclude _minified output dirs and _build dirs
    lua_files = [
        f for f in lua_files
        if "_minified" not in f.parts and "_build" not in f.parts
    ]

    if not lua_files:
        print(f"{YELLOW}No .lua files found in {folder}{RESET}")
        return

    out_dir = folder / "_minified"
    out_dir.mkdir(exist_ok=True)

    print(f"\n{BOLD}{CYAN}VladgeMinifier Batch Mode{RESET}")
    print(f"  Files:   {len(lua_files)}")
    print(f"  Level:   {level} - {LEVEL_NAMES.get(level, '?')}")
    print(f"  Workers: {workers}\n")

    total_before = 0
    total_after = 0
    errors = 0
    t0 = time.perf_counter()

    args = [(f, level, obfuscate, multiline, inline_functions, lua53_floor) for f in lua_files]
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_batch_worker, a): a for a in args}
        done = 0
        for future in as_completed(futures):
            path, result, stats, error = future.result()
            done += 1
            rel = Path(path).relative_to(folder)

            if error:
                errors += 1
                print(f"  {RED}[!] {rel}: {error}{RESET}")
                continue

            # Mirror directory structure in output
            out_path = out_dir / rel
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(result, encoding="utf-8")

            if deploy:
                deploy_dir = Path(deploy)
                from src.core.deployer import deploy_to_target
                deploy_to_target(result, input_path.name, deploy_dir)

            total_before += stats.original_size
            total_after += stats.final_size

            if not stats.semantic_ok:
                status = f"{RED}[BROKEN]{RESET}"
                errors += 1
            elif stats.under_limit:
                status = f"{GREEN}[OK]{RESET}"
            else:
                status = f"{RED}[!!]{RESET}"
            if not quiet:
                print(f"  [{done:>3}/{len(lua_files)}] {status} {rel}  "
                      f"{stats.original_size:>6,} -> {stats.final_size:>5,} "
                      f"({stats.ratio:.0f}%)")

    elapsed = (time.perf_counter() - t0) * 1000
    saved = total_before - total_after
    ratio = (saved / total_before * 100) if total_before else 0

    print(f"\n{BOLD}{'-'*50}{RESET}")
    print(f"  Total:   {total_before:,} -> {total_after:,} chars")
    print(f"  Saved:   {GREEN}{saved:,} chars ({ratio:.1f}%){RESET}")
    print(f"  Time:    {elapsed:.0f}ms")
    if errors:
        print(f"  Errors:  {RED}{errors}{RESET}")
    print(f"  Output:  {out_dir}\n")


def main():
    # Enable ANSI on Windows
    if sys.platform == "win32":
        os.system("")

    parser = argparse.ArgumentParser(
        prog="vladgeminifier",
        description=f"VladgeMinifier v{__version__} - Stormworks Lua Minifier",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"VladgeMinifier {__version__}")
    parser.add_argument("input", help="Lua file or folder (with --batch)")
    parser.add_argument(
        "--level",
        type=int,
        choices=[1, 2, 3, 4],
        default=3,
        help="Minification level (1=Strip, 2=Locals, 3=Globals, 4=Ultimate)"
    )
    parser.add_argument("--clipboard", action="store_true",
                        help="Copy result to clipboard")
    parser.add_argument("--no-save", action="store_true",
                        help="Do not write an output file")
    parser.add_argument("--save", metavar="PATH",
                        help="Output path (default: _minified/<name>)")
    parser.add_argument("--deploy", metavar="DIR",
                        help="Deploy output file(s) to the specified directory")
    parser.add_argument("--batch", action="store_true",
                        help="Process all .lua files in a folder")
    parser.add_argument("--workers", type=int, default=None,
                        help="Parallel workers for batch (default: CPU count)")
    parser.add_argument("--obfuscate", action="store_true",
                        help="Scramble variables and encrypt strings (increases size)")
    parser.add_argument("--multiline", choices=["off", "statements", "preserve"], default="off",
                        help="Output mode: off=single line, statements=line breaks, preserve=source newlines")
    parser.add_argument("--inline-functions", action="store_true",
                        help="Inline small local functions (L4, experimental)")
    parser.add_argument("--lua53-floor", action="store_true",
                        help="Enable math.floor -> (x)//1 golfing (opt-in)")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress output")

    args = parser.parse_args()

    input_path = Path(args.input)
    workers = args.workers or os.cpu_count() or 4

    if args.batch or input_path.is_dir():
        if not input_path.is_dir():
            print(f"{RED}Error: {input_path} is not a directory{RESET}")
            sys.exit(1)
        process_batch(input_path, args.level, workers, args.deploy, args.quiet, args.obfuscate,
                      args.multiline, args.inline_functions, args.lua53_floor)
    else:
        if not input_path.exists():
            print(f"{RED}Error: file not found: {input_path}{RESET}")
            sys.exit(1)
        if not input_path.suffix.lower() == ".lua":
            print(f"{YELLOW}Warning: {input_path} is not a .lua file{RESET}")
        process_single(input_path, args.level, args.clipboard, args.no_save, args.save, args.deploy, args.quiet,
                       args.obfuscate, args.multiline, args.inline_functions, args.lua53_floor)


if __name__ == "__main__":
    main()
