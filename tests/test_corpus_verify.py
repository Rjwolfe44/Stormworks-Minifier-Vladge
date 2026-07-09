"""Corpus verification: real Code Folder scripts must parse and pass semantic checks."""

from pathlib import Path
import pytest
from src.core.minifier import minify
from tests.helpers_verify import verify_minified

CODE_FOLDER = Path(
    r"C:\Users\rjwol\Proton Drive\rjwolfe44h\My files\Personal Files\General Code Folder\Code Folder"
)

pytestmark = pytest.mark.skipif(
    not CODE_FOLDER.exists(),
    reason="Code Folder not available on this machine",
)


def _iter_scripts():
    for p in sorted(CODE_FOLDER.glob("*.lua")):
        yield p


@pytest.mark.parametrize("path", list(_iter_scripts()) or [None], ids=lambda p: p.name if p else "none")
def test_corpus_semantic_l2(path):
    if path is None:
        pytest.skip("no scripts")
    source = path.read_text(encoding="utf-8", errors="replace")
    result, stats = minify(source, level=2, root_dir=str(CODE_FOLDER))
    assert stats.semantic_ok, stats.semantic_errors
    assert not verify_minified(result)


@pytest.mark.parametrize("path", list(_iter_scripts()) or [None], ids=lambda p: p.name if p else "none")
def test_corpus_semantic_l4(path):
    if path is None:
        pytest.skip("no scripts")
    source = path.read_text(encoding="utf-8", errors="replace")
    result, stats = minify(source, level=4, root_dir=str(CODE_FOLDER))
    assert stats.semantic_ok, stats.semantic_errors
    assert not verify_minified(result)
