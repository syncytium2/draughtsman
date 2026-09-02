"""The gallery reproduces from this repo alone, and something has to check it.

`examples/gallery/README.md` says the models are written out in full "so the
gallery reproduces from this repo alone: no torchvision, no downloads, no pinned
third-party version." That was true when written and stopped being true without
anyone noticing: `whisper_tiny.py` imported numpy for one `np.log` of one scalar.

**It went unnoticed for six hours and three pushes because it fails only where
numpy is absent.** Every developer machine here has numpy pulled in by something
else, so the suite was green locally and red on CI, and two sessions pushed onto
a red main without the failure being theirs. A claim that only CI can test is a
claim the author cannot act on.

So this asserts the import surface directly, from the source, with no imports
performed — it fails on the machine of whoever adds the dependency, in the same
run as their change.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

GALLERY = Path(__file__).resolve().parent.parent / "examples" / "gallery"

#: Everything the gallery is allowed to reach for. `torch` is the subject; the
#: rest is the standard library, which travels with the interpreter.
ALLOWED = {"torch", "draughtsman"} | set(sys.stdlib_module_names)


def _roots(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name.partition(".")[0]
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                yield node.module.partition(".")[0]


@pytest.mark.parametrize("path", sorted(GALLERY.glob("*.py")),
                         ids=lambda p: p.name)
def test_a_gallery_model_imports_nothing_but_torch_and_the_stdlib(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    outside = sorted({r for r in _roots(tree) if r not in ALLOWED})
    assert not outside, (
        f"{path.name} imports {', '.join(outside)}, which the gallery's README "
        "promises it does not need. Either write the thing out — numpy was one "
        "`np.log` of one scalar and `math` does it — or change the README and "
        "this test together, deliberately."
    )


def test_the_check_would_have_caught_the_numpy_import():
    """The guard is only worth having if it fires. This is the exact source line
    that was live on main for six hours."""
    tree = ast.parse("import numpy as np\nx = np.log(10000)\n")
    assert [r for r in _roots(tree) if r not in ALLOWED] == ["numpy"]
