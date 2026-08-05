"""
VladgeMinifier - SW Bundler (legacy).

Prefer ``src.core.passes.combiner.bundle_requires`` — this module is retained
only for older imports. Circular requires return the cached module id via the
combiner; do not use the old ``nil`` stub behaviour.
"""

from pathlib import Path

from .passes.combiner import bundle_requires


def bundle_code(source_code: str, base_dir: Path) -> str:
    """Inline require() calls relative to base_dir (combiner implementation)."""
    return bundle_requires(source_code, base_dir)
