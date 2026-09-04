"""Text measurement without a font engine.

Layout needs a box width before there is anything to measure it with, and pulling
in a rasteriser to size a dozen labels would be a poor trade. These are Helvetica's
own advance widths (units per 1000 em), which every sans fallback in the stack is
close enough to that a 6px padding absorbs the difference.

The render pins the font stack inline for the same reason: if the embedding page
substituted a wider face, boxes sized here would be too small for their own labels
— which is exactly the class of defect (a label struck through by its own figure)
that SPEC.md §4 records from the hand-laid draft.
"""

from __future__ import annotations

# QUOTED, AND THE QUOTES ARE LOAD-BEARING. `Helvetica Neue` unquoted is not a
# valid CSS family name, and several SVG engines drop the whole declaration
# rather than the one bad token -- falling through to the engine default, which
# on Linux is DejaVu Sans, wider than Helvetica at every size. An outside
# reviewer rasterised the gallery that way and the ResNet legend overran its own
# viewBox.
#
# SINGLE quotes, because this string is interpolated into `style="..."` on every
# text element. Double quotes would close the XML attribute and break the file --
# which is the failure mode where "I quoted the font name" produces something far
# worse than the unquoted version it fixed.
FONT_STACK = "'Helvetica Neue', Helvetica, Arial, sans-serif"

_W = {
    " ": 278, "!": 278, '"': 355, "#": 556, "$": 556, "%": 889, "&": 667,
    "'": 191, "(": 333, ")": 333, "*": 389, "+": 584, ",": 278, "-": 333,
    ".": 278, "/": 278, ":": 278, ";": 278, "<": 584, "=": 584, ">": 584,
    "?": 556, "@": 1015, "[": 278, "\\": 278, "]": 278, "^": 469, "_": 556,
    "`": 333, "{": 334, "|": 260, "}": 334, "~": 584,
    "A": 667, "B": 667, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
    "H": 722, "I": 278, "J": 500, "K": 667, "L": 556, "M": 833, "N": 722,
    "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722,
    "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611,
    "a": 556, "b": 556, "c": 500, "d": 556, "e": 556, "f": 278, "g": 556,
    "h": 556, "i": 222, "j": 222, "k": 500, "l": 222, "m": 833, "n": 556,
    "o": 556, "p": 556, "q": 556, "r": 333, "s": 500, "t": 278, "u": 556,
    "v": 500, "w": 722, "x": 500, "y": 500, "z": 500,
}
for _d in "0123456789":
    _W[_d] = 556

# THE NON-ASCII THE GALLERY ACTUALLY USES, MEASURED RATHER THAN ASSUMED.
# `_DEFAULT` below estimated all of these at 556, and `×` alone appears 146 times
# across the ten figures -- every shape string carries one. These four are
# Helvetica/Arial's own advances and are not guesses.
_W["\u00d7"] = 584        # × MULTIPLICATION SIGN, like + = < in this face
_W["\u2014"] = 1000       # — EM DASH
_W["\u2013"] = 556        # – EN DASH
_W["\u00b7"] = 278        # · MIDDLE DOT

# ANYTHING ELSE IS AN ESTIMATE, AND `unmeasured()` NAMES WHICH. The remaining
# glyphs in the gallery -- σ ε μ → ₁₂₃₄₅₆ √ ⊙ -- have no advance here and are not
# reliably present in the pinned stack either. The estimate no longer decides the
# rendered width: every <text> now carries `textLength`, so the number computed
# here is the number that renders. See render.py `_text`.
_DEFAULT = 556
_BOLD = 1.06          # Helvetica-Bold runs a little wider


def width(text: str, size: float, *, bold: bool = False) -> float:
    total = sum(_W.get(ch, _DEFAULT) for ch in text)
    return round(total / 1000.0 * size * (_BOLD if bold else 1.0), 3)


def unmeasured(text: str) -> set[str]:
    """The characters in `text` with no advance width here, so they were
    estimated at `_DEFAULT`.

    A SILENT ESTIMATE IS THE THING THIS FILE IS FOR. `width()` cannot fail on an
    unknown glyph -- it must return a number -- so the only way the estimate can
    be held to account is for something else to be able to ask which characters
    were guessed. `tests/test_render.py` asks it of every string in the gallery.
    """
    return {ch for ch in text if ch not in _W}


def escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))
