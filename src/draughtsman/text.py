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

FONT_STACK = "Helvetica Neue, Helvetica, Arial, sans-serif"

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

_DEFAULT = 556        # anything outside Latin-1: ×, σ, →, em dash
_BOLD = 1.06          # Helvetica-Bold runs a little wider


def width(text: str, size: float, *, bold: bool = False) -> float:
    total = sum(_W.get(ch, _DEFAULT) for ch in text)
    return round(total / 1000.0 * size * (_BOLD if bold else 1.0), 3)


def escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))
