#!/usr/bin/env python3
"""Report the size a figure's type will ACTUALLY render at.

    tools/measure_type.py examples/gallery/*/figure.svg
    tools/measure_type.py --width 1002 examples/gallery/dual/figure.svg
    tools/measure_type.py --print 3.5in examples/gallery/unet/figure.svg
    tools/measure_type.py --floor 6pt --print 6in examples/gallery/*/figure.svg

Exit 1 when anything falls under `--floor`, so it works as a gate.

WHY THIS EXISTS
---------------
Effective type size is one expression:

    rendered = unit_size x display_width / viewBox_width

Three inputs, and they are easy to get wrong together. In one evening this
repository got it wrong three ways:

  - the page stretched a 1594-unit figure into a 1460px column, a 0.92x
    REDUCTION, so 9.5-unit labels rendered at 8.7px;
  - `width_budget` computed the print floor from DETAIL_SIZE while the smallest
    type in the figure was actually a 7-unit count badge;
  - and once the SVG began declaring `width="6in"` for print, a browser honoured
    it at 576px and the same labels came out at 9.8px on a page.

Every one of those was invisible to the eye and obvious to arithmetic. `check`
already refuses a figure that would print under its floor; this answers the same
question for any display width, including a slide or a web page, and it answers
it about a RENDERED file rather than about the constants that produced it.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Set only by `selftest`, to break the scale on purpose and require the answer
# to move. A test that cannot tell a working expression from a broken one is not
# testing the expression.
_MUTATE = False

CSS_PX_PER_IN = 96.0
PT_PER_IN = 72.0
_UNIT_PX = {"px": 1.0, "in": CSS_PX_PER_IN, "pt": CSS_PX_PER_IN / PT_PER_IN,
            "mm": CSS_PX_PER_IN / 25.4, "cm": CSS_PX_PER_IN / 2.54}


class Undeterminable(Exception):
    """The type size cannot be computed from this file."""


def length_px(text: str) -> float:
    m = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*(px|in|pt|mm|cm)?\s*", str(text))
    if not m:
        raise SystemExit(f"{text!r} is not a length; try '6in', '450px' or '9pt'")
    return float(m.group(1)) * _UNIT_PX[m.group(2) or "px"]


def viewbox_width(svg: str) -> float:
    m = re.search(r'viewBox="\s*[\d.-]+\s+[\d.-]+\s+([\d.]+)', svg)
    if not m:
        raise Undeterminable("no viewBox, so the figure states no coordinate "
                             "system and nothing can be scaled against it")
    return float(m.group(1))


def declared_width(svg: str) -> str | None:
    m = re.search(r"<svg[^>]*?\swidth=\"([^\"]+)\"", svg)
    return m.group(1) if m else None


# SVG SPELLS font-size TWO WAYS AND THE FIRST VERSION OF THIS SAW ONE.
#
# It matched `font-size:7px` — a CSS declaration, with a colon and a literal px —
# and was blind to `font-size="7"`, the presentation attribute, which is SVG's
# own spelling and what most producers emit. draughtsman happens to write the CSS
# form, so this tool was green on the only files anyone had pointed it at.
# Reported by murderboard-7a, who pointed it at a file this repository did not
# write.
_SIZE_RE = re.compile(
    r"font-size\s*[:=]\s*[\"']?\s*([\d.]+)\s*(px|pt|pc|mm|cm|in|em|rem|%)?",
    re.I)
# A user unit IS a px in SVG. Physical units convert; em, rem and % depend on
# context this tool cannot see, so they are refused rather than guessed.
_TO_USER = {None: 1.0, "px": 1.0, "pt": 96.0 / 72.0, "pc": 16.0,
            "mm": 96.0 / 25.4, "cm": 96.0 / 2.54, "in": 96.0}


def type_sizes(svg: str) -> list[float]:
    """Every distinct font-size in the file, in user units."""
    out = set()
    for value, unit in _SIZE_RE.findall(svg):
        unit = (unit or "").lower() or None
        if unit in ("em", "rem", "%"):
            raise Undeterminable(
                f"font-size is relative ({value}{unit}), which depends on "
                "context this tool cannot see")
        out.add(float(value) * _TO_USER[unit])
    return sorted(out)


def measure(path: Path, display_px: float | None, floor_px: float | None):
    # THE FORMAT LIMIT IS ENFORCED HERE, NOT BY AN EXCEPTION ESCAPING.
    #
    # This gate reads SVG and says so. Before this, a PNG or a binary PDF died in
    # `read_text` with a UnicodeDecodeError: exit 1, which was the right status
    # for the wrong reason. Three costs, and the first is the one that would have
    # bitten later — nothing pinned it, so `errors="replace"` on this read would
    # have turned every PNG into a silent pass with no test noticing. An
    # ASCII-clean PDF meanwhile decoded fine and got a named refusal, so one
    # declared limit had two behaviours depending on whether the bytes happened
    # to be UTF-8. And in CI a traceback reads as a broken tool rather than as
    # the gate declining a file that is out of scope.
    #
    # Found by murderboard-7a, running it on files this repository did not write,
    # after I claimed in writing that this branch already handled them.
    try:
        svg = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print(f"\n{path}")
        print("  CANNOT DETERMINE: not a text file. This gate reads SVG; a PNG "
              "or PDF figure has to be measured by something else.")
        return [(0.0, 0.0)]
    except OSError as exc:
        # A SEPARATE SENTENCE, BECAUSE IT IS A SEPARATE PROBLEM. Both arms used
        # to print the format remedy, so a missing path was told that this gate
        # reads SVG and that a PNG needs another tool — true, and no help at all
        # to someone who has mistyped a filename. No fixture reached this arm, so
        # nothing had ever read what it says.
        print(f"\n{path}")
        print(f"  CANNOT DETERMINE: cannot read this file ({exc.strerror or exc}).")
        return [(0.0, 0.0)]
    try:
        units = viewbox_width(svg)
    except Undeterminable as exc:
        print(f"\n{path}")
        print(f"  CANNOT DETERMINE: {exc}")
        return [(0.0, 0.0)]
    declared = declared_width(svg)
    intrinsic = length_px(declared) if declared else None
    shown = display_px if display_px is not None else intrinsic
    if shown is None:
        raise SystemExit(f"{path}: no width declared; pass --width or --print")
    scale = 1.0 if _MUTATE else shown / units
    print(f"\n{path}")
    print(f"  {units:.0f} units wide, declared {declared!r}"
          + (f" ({intrinsic:.0f}px)" if intrinsic else ""))
    print(f"  shown at {shown:.0f}px  ->  {scale:.2f}x")
    try:
        found = type_sizes(svg)
    except Undeterminable as exc:
        print(f"  CANNOT DETERMINE: {exc}")
        return [(0.0, 0.0)]
    # ZERO SIZES IS NOT CLEAN, IT IS UNMEASURED, AND IT MUST FAIL CLOSED.
    #
    # Before this, a figure whose every label was spelled in a form the pattern
    # did not match printed `ok` — indistinguishable from a run that had measured
    # and found nothing wrong. That is a claim of absence resting on an
    # instrument that could not have registered the presence, which is the exact
    # defect this tool was written to catch, in this tool. A PNG or a PDF lands
    # here too, and must refuse rather than pass.
    if not found:
        print("  CANNOT DETERMINE: no font-size found. This is a refusal, not a "
              "pass — an unreadable figure and an unparseable one look the same "
              "from here.")
        return [(0.0, 0.0)]
    under = []
    for u in found:
        px = u * scale
        pt = px * PT_PER_IN / CSS_PX_PER_IN
        bad = floor_px is not None and px < floor_px - 1e-9
        if bad:
            under.append((u, px))
        print(f"    {u:>5.1f}u  ->  {px:6.2f}px  ({pt:5.2f}pt){'   UNDER FLOOR' if bad else ''}")
    return under


# A FIXTURE WITH KNOWN ANSWERS. 400 units wide, one 10-unit size and one 20-unit
# size, so every expectation below is arithmetic anyone can check by hand.
_FIXTURE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 100" '
    'width="400" height="100">'
    '<text style="font-size:10.0px">body</text>'
    '<text style="font-size:20.0px">head</text></svg>'
)
# HOW TO WRITE A FIXTURE, since this file has now got it wrong three times.
#
# A fixture drawn from the only producer you have is not a fixture, it is a
# mirror — it is green on exactly the input class the tool already handles. That
# went wrong here with CSS-only spellings, then with all-text files, then with a
# read arm no file reached.
#
# The rule cannot bootstrap from inside the thing it is about: your fixtures come
# from your producer because your producer is all you have. murderboard-7a's
# operational form is the one to follow, because a single session can act on it
# alone: A FIXTURE HAS TO COME FROM A SECOND PRODUCER, AND IF YOU ONLY HAVE ONE,
# WRITE THE FILE BY HAND SPECIFICALLY TO BE UNLIKE YOUR OWN OUTPUT.
#
# THE SAME FIGURE IN SVG'S OWN SPELLING. The first selftest used only the CSS
# form above — the form draughtsman happens to emit — so it was green while the
# tool was blind to every figure written the other way. A fixture drawn from the
# only producer you have is not a fixture, it is a mirror.
_FIXTURE_ATTR = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 100" '
    'width="400" height="100">'
    '<text font-size="10">body</text>'
    '<text font-size="20">head</text></svg>'
)
_FIXTURE_NO_TYPE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 100" '
    'width="400" height="100"><rect width="10" height="10"/></svg>'
)


def selftest() -> int:
    """Prove this can fail, not merely that it passes.

    A GREEN SELFTEST IS AN UNCHECKED CLAIM until something has broken the code
    and watched it go red. That is armory's standard and its reason is exactly
    this file's reason: a gate nobody has seen refuse is a gate nobody can rely
    on refusing. So the cases below include the failing direction, and the last
    one breaks the arithmetic on purpose and requires the result to change.
    """
    import tempfile
    failures: list[str] = []

    def ok(cond, msg):
        if not cond:
            failures.append(msg)

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "fixture.svg"
        p.write_text(_FIXTURE, encoding="utf-8")

        ok(viewbox_width(_FIXTURE) == 400.0, "viewBox width misread")
        ok(declared_width(_FIXTURE) == "400", "declared width misread")
        ok(type_sizes(_FIXTURE) == [10.0, 20.0], "type sizes misread")

        # BOTH SPELLINGS MUST AGREE. `font-size="10"` is SVG's presentation
        # attribute and the form most producers emit; `font-size:10px` is the CSS
        # declaration. A tool that reads one and silently reports nothing for the
        # other is the defect this file exists to catch.
        ok(type_sizes(_FIXTURE_ATTR) == [10.0, 20.0],
           "the SVG presentation attribute form was not read")
        ok(type_sizes('<text font-size="9pt"/>') == [12.0],
           "a pt size was not converted to user units")
        try:
            type_sizes('<text font-size="1.2em"/>')
            ok(False, "a relative size was accepted; it cannot be resolved here")
        except Undeterminable:
            pass

        # AND FINDING NOTHING MUST REFUSE, NOT PASS.
        q = Path(td) / "none.svg"
        q.write_text(_FIXTURE_NO_TYPE, encoding="utf-8")
        ok(measure(q, 400.0, 6.0) != [],
           "a figure with no readable type reported clean — an unreadable figure "
           "and an unparseable one must not look the same from here")
        ok(main([str(q), "--width", "400px", "--floor", "6pt"]) == 1,
           "a figure with no readable type exited 0")

        # NON-TEXT AND NON-SVG, which every earlier fixture here was not.
        #
        # The declared limit is "this gate reads SVG". Until these existed it was
        # enforced by a UnicodeDecodeError escaping — exit 1 for the wrong
        # reason, unpinned, and reading as a broken tool in CI. Every fixture
        # above is a text file, so the branch that handles bytes had never once
        # been run. That is the mirror again, one level down: a selftest is only
        # as wide as the inputs someone thought to write.
        b = Path(td) / "figure.png"
        b.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
        ok(measure(b, 400.0, 6.0) != [],
           "a binary file did not refuse — the SVG-only limit is not enforced")
        ok(main([str(b), "--width", "400px", "--floor", "6pt"]) == 1,
           "a binary file exited 0")

        # AND THE ARM NO FIXTURE HAD EVER REACHED. Until this existed, both
        # read failures printed the format remedy, and nobody had read the one
        # for a path that simply is not there.
        missing = Path(td) / "does-not-exist.svg"
        ok(measure(missing, 400.0, 6.0) != [],
           "a path that does not exist did not refuse")
        ok(main([str(missing), "--width", "400px", "--floor", "6pt"]) == 1,
           "a path that does not exist exited 0")

        n = Path(td) / "noviewbox.svg"
        n.write_text('<svg width="400"><text font-size="9">x</text></svg>',
                     encoding="utf-8")
        ok(measure(n, 400.0, 6.0) != [],
           "an SVG with no viewBox did not refuse; there is no scale to measure "
           "against and a number here would be invented")

        # units -> px, the one expression this tool exists for
        ok(abs(length_px("6in") - 576.0) < 1e-9, "6in is 576 CSS px")
        ok(abs(length_px("9pt") - 12.0) < 1e-9, "9pt is 12 CSS px")

        # at 800px the figure is drawn 2x, so 10u is 20px and 20u is 40px
        under = measure(p, 800.0, None)
        ok(under == [], "no floor given, so nothing may be reported under it")

        # THE FAILING DIRECTION. At 200px the scale is 0.5x and 10u is 5px,
        # which is under a 6px floor. If this does not report, the gate is
        # decorative and every green run above it means nothing.
        under = measure(p, 200.0, 6.0)
        ok(under and abs(under[0][1] - 5.0) < 1e-9,
           "a 5px label under a 6px floor was NOT reported — the gate cannot fire")

        # and the same run through the command line must exit 1
        ok(main([str(p), "--width", "200px", "--floor", "6pt"]) == 1,
           "under the floor, the exit status was not 1")
        ok(main([str(p), "--width", "800px", "--floor", "6pt"]) == 0,
           "above the floor, the exit status was not 0")

        # MUTATION: break the expression and require the answer to move. If the
        # scale is ignored, 10u would report as 10px at every width and the
        # 200px case above would silently pass.
        global _MUTATE
        _MUTATE = True
        try:
            broken = measure(p, 200.0, 6.0)
        finally:
            _MUTATE = False
        ok(broken == [], "mutating the scale did not change the result, so the "
                         "cases above are not testing the arithmetic they claim")

    for f in failures:
        print(f"  FAIL: {f}")
    print(f"selftest: {'FAILED' if failures else 'ok'} "
          f"({len(failures)} failure{'s' if len(failures) != 1 else ''})")
    return 1 if failures else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="*", type=Path)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--width", help="display width, e.g. 1002px")
    g.add_argument("--print", dest="printed", help="physical width, e.g. 6in")
    ap.add_argument("--floor", help="fail below this, e.g. 6pt")
    ap.add_argument("--selftest", action="store_true",
                    help="check this tool against a fixture with known answers")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.files:
        ap.error("give at least one SVG, or --selftest")

    shown = length_px(a.width or a.printed) if (a.width or a.printed) else None
    floor = length_px(a.floor) if a.floor else None
    failed = False
    for p in a.files:
        if measure(p, shown, floor):
            failed = True
    if floor is not None:
        print(f"\n{'FAIL' if failed else 'ok'}: floor {a.floor}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
