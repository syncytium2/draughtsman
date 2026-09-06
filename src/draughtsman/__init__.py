"""draughtsman — readable architecture diagrams for PyTorch models.

Three stages, and the split between them is the design (SPEC.md §4):

    model -> [trace] -> graph.json -> [abstract] -> spec.json -> [render] -> figure.svg
              facts                    judgement                  deterministic

``trace`` needs torch. ``check`` and ``render`` need neither torch nor any system
binary, so a machine that only draws a figure installs almost nothing.
"""

# THE ONLY PLACE THIS NUMBER IS WRITTEN. `pyproject.toml` declares the version
# dynamic and reads it from here, so a build, an import and `draughtsman
# --version` cannot disagree.
#
# WHY 0.1.2 AND NOT 0.1.1. `v0.1.1` is already a tag, a GitHub release and a
# Zenodo deposit, taken at `577bf92` -- and that snapshot says 0.1.0 here,
# because the releases were cut without ever bumping this line. Calling the
# current tree 0.1.1 would put a second, different tree behind a number already
# archived under the first. 0.1.2 is the lowest number that can be tagged,
# archived and uploaded describing one tree. 0.1.1 will never exist on PyPI.
__version__ = "0.1.3"

FORMAT = "0"  # bumped when graph.json / spec.json change shape

__all__ = ["FORMAT", "__version__"]
