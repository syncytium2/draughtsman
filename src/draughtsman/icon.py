"""Stage 3b — the same figure at a size where nothing can be read.

    draughtsman render spec.json --icon 420x104 -o icon.svg

WHY THIS IS NOT A SMALLER FIGURE
--------------------------------
`check` refuses a figure whose type would print under its stated floor. That is
the right answer when a figure is going somewhere type can survive. It has
nothing to say about a card, a favicon or a shelf tile, where no type survives at
any size: at 420x104 every figure in this gallery lands between 1.6px and 3.6px
of body type, and the honest response is not a smaller floor but no text.

So an icon is not a scaled figure. It is the same drawing with everything that
cannot be read at that size removed, cropped to what is left. What survives is
shape — the sequence of stages, their relative bulk, and the merges and skips
between them — which is the only thing a mark that size was ever going to carry.

The alternative, and it is what the estate did instead: tonydefazio.com's
draughtsman card carries a hand-drawn schematic, because shipping a clean,
authoritative-looking figure that conveys none of the architecture is the exact
defect this repository convicts other tools of. This is what lets a real figure
take that slot.

WHAT IT REMOVES, AND WHY EACH ONE IS NOT OPTIONAL
-------------------------------------------------
Every rule here comes from a defect that shipped in a hand-built icon and was
caught by rasterising it and looking, not by measuring it:

  text          the point. Labels at 1.8px are grey noise that reads as damage.
  legend        prose, and its swatch survived `layout.legend: false` -- that
                flag suppresses the rows `_legend` returns, not the glyph row
                `render` appends to them, so a stray square sat in the corner.
  empty stages  a stage that draws only text becomes an empty group when the
                text goes, and its edges survive as ARROWS POINTING AT NOTHING.
                lenet ended with three trailing off the right.
  sub-pixel     `tube` draws 78 three-unit marks; at 0.33x they are one pixel
                each and read as dirt on the glass. Same rule as the text.

WHAT IT DOES NOT DO, STATED HERE SO IT IS NOT DISCOVERED
--------------------------------------------------------
It post-processes a rendered figure; it does not re-solve the layout. Boxes were
sized to hold text that is no longer drawn, so a boxed figure comes out with more
empty box than it needs. A glyph figure (`layout.chrome: "none"`) has no such
slack and comes out tight. Re-laying out without the text is a renderer change
and a larger claim.
"""
from __future__ import annotations

import re

#: Elements small enough that they cannot resolve at icon scale. Removed for the
#: same reason the text is: what cannot be read is noise, and shipping noise is
#: worse than shipping nothing.
SUBPIXEL_CLASSES = ("ds-mark", "ds-mark-bar")

#: Fraction of the drawn extent added as breathing room on each side.
MARGIN = 0.02

# WHETHER A MARK READS, AS A NUMBER RATHER THAN AS SOMEONE'S OPINION.
#
# `render --icon` has always printed the scale it drew at and nothing has ever
# consumed it, so a mark that cannot be seen shipped exactly as quietly as one
# that can. The other checks here ask whether an icon is COMPLETE, UNCROPPED and
# TEXTLESS -- all necessary, none of them the question a reader asks, which is
# whether they can make it out.
#
# MEASURED, 2026-09-04, all ten committed models in a 192x96 slot (1x2in at
# 96dpi), by rasterising each one and looking at it:
#
#     mlp     0.3997  |  read
#     lenet   0.3940  |
#     lstm    0.2975  |
#     ------------------ gap 0.086 --------------------------- READS_AT = 0.25
#     dual    0.2114  |  marginal
#     tube    0.2047  |
#     ------------------ gap 0.031 ------------------------- NOISE_BELOW = 0.19
#     resnet  0.1737  |  do not read: flecks and hairlines
#     transformer 0.1483
#     vae     0.1358  |
#     unet    0.1241  |  dirt on the glass
#     whisper 0.1143  |
#
# BOTH NUMBERS SIT IN THE MIDDLE OF A REAL GAP, and that is the whole reason
# they are these numbers. The three bands are separated by 0.086 and 0.031 of
# empty range; a boundary in the middle of one survives a model landing near it,
# where a boundary drawn against its nearest neighbour is an artefact of the
# sample rather than a fact about legibility.
#
# THE FIRST ATTEMPT USED 0.30 AND 0.20 AND WAS WRONG, in the way this repository
# keeps finding things wrong. Those came from the printed table, where the CLI
# renders the scale to two places -- and `lstm`, printed as `0.30x`, is actually
# 0.2975. A boundary at 0.30 put the lowest mark anyone had confirmed READS on
# the wrong side of the line, by 0.0025. Rounding for a person to read and
# thresholding for a machine to decide are different jobs, and a number that
# does both silently does the second one badly.
#
# TWO THINGS THIS IS NOT. It is not a refusal: seven of the ten committed marks
# are under READS_AT, the repository ships them anyway as the honest record of
# what this size costs, and a gate that fails the majority of the corpus it
# measures is one somebody turns off. And it is not slot-independent -- the
# scale is a ratio, so it travels, but the LOOKING that produced these numbers
# happened at one size. A different slot deserves its own look before these are
# trusted there.
READS_AT = 0.25
NOISE_BELOW = 0.19

READS, MARGINAL, NOISE = "reads", "marginal", "does not read"


def verdict(scale: float) -> str:
    """`READS`, `MARGINAL` or `NOISE` for a scale `render_icon` reported."""
    if scale >= READS_AT:
        return READS
    if scale >= NOISE_BELOW:
        return MARGINAL
    return NOISE

NUM = r"-?\d+\.?\d*"
_DRAWN = re.compile(r"<(rect|path|polygon|polyline|circle|ellipse)\b")


class IconError(ValueError):
    """The figure has nothing left once the unreadable is removed."""


def parse_size(text: str) -> tuple[float, float]:
    """`420x104` -> (420.0, 104.0). Raises on anything else."""
    m = re.fullmatch(r"\s*(%s)\s*[xX*]\s*(%s)\s*" % (NUM, NUM), text or "")
    if not m:
        raise IconError(f"icon size {text!r} is not WIDTHxHEIGHT, e.g. 420x104")
    w, h = float(m.group(1)), float(m.group(2))
    if w <= 0 or h <= 0:
        raise IconError(f"icon size {text!r} must be positive")
    return w, h


def _flatten(d: str) -> list[tuple[float, float]]:
    """Path data to points, sampling curves.

    A control point is not on the curve. Reading bounds off controls inflates the
    crop and lands the drawing small and off-centre inside it.
    """
    toks = re.findall(r"[MLQCZmlqcz]|%s" % NUM, d)
    pts: list[tuple[float, float]] = []
    i, cur, cmd = 0, (0.0, 0.0), "M"
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd, i = t.upper(), i + 1
            continue
        if cmd in ("M", "L"):
            x, y = float(toks[i]), float(toks[i + 1])
            i += 2
            pts.append((x, y))
            cur = (x, y)
        elif cmd in ("Q", "C"):
            n = 4 if cmd == "Q" else 6
            v = [float(toks[i + j]) for j in range(n)]
            i += n
            end = (v[-2], v[-1])
            for k in range(1, 17):
                s = k / 16
                if cmd == "Q":
                    px = (1 - s) ** 2 * cur[0] + 2 * (1 - s) * s * v[0] + s * s * v[2]
                    py = (1 - s) ** 2 * cur[1] + 2 * (1 - s) * s * v[1] + s * s * v[3]
                else:
                    m0, m1 = (1 - s) ** 3, 3 * (1 - s) ** 2 * s
                    m2, m3 = 3 * (1 - s) * s * s, s ** 3
                    px = m0 * cur[0] + m1 * v[0] + m2 * v[2] + m3 * v[4]
                    py = m0 * cur[1] + m1 * v[1] + m2 * v[3] + m3 * v[5]
                pts.append((px, py))
            cur = end
        else:
            i += 1
    return pts


def _body_offset(svg: str) -> tuple[float, float]:
    """The translate on `<g class="ds-body">`, which everything is drawn inside.

    MEASURING INSIDE A TRANSFORM AND CROPPING OUTSIDE IT IS OFF BY THE
    TRANSFORM, and it fails quietly: the viewBox is a legal rectangle of the
    right size in the wrong place, so the icon renders and is simply clipped
    along one edge. The offset is the head band, which is 22 units for a figure
    with no caption and 36 with one, so the same code cropped a little or a lot
    depending on a spec field nothing here reads.

    Caught by rasterising two icons that had identical viewBoxes and identical
    element counts and did not look the same.
    """
    m = re.search(r'<g class="ds-body"[^>]*transform="translate\(\s*(%s)[\s,]+(%s)\s*\)"'
                  % (NUM, NUM), svg)
    return (float(m.group(1)), float(m.group(2))) if m else (0.0, 0.0)


def _drawn_bounds(svg: str) -> tuple[float, float, float, float]:
    """Bounds of everything actually drawn, in the ROOT coordinate space.

    `<defs>` is excluded: the arrowhead marker lives there at its own tiny
    coordinates, and including it drags the box to the origin and renders the
    icon in a corner of its own frame.
    """
    body = re.sub(r"<defs>.*?</defs>", "", svg, flags=re.S)
    ox, oy = _body_offset(svg)
    xs: list[float] = []
    ys: list[float] = []
    for m in re.finditer(r"<rect\b([^>]*)>", body):
        a = m.group(1)
        try:
            x = float(re.search(r'\bx="(%s)"' % NUM, a).group(1))
            y = float(re.search(r'\by="(%s)"' % NUM, a).group(1))
            w = float(re.search(r'\bwidth="(%s)"' % NUM, a).group(1))
            h = float(re.search(r'\bheight="(%s)"' % NUM, a).group(1))
        except AttributeError:
            continue
        xs += [x, x + w]
        ys += [y, y + h]
    for m in re.finditer(r'\bd="([^"]+)"', body):
        for px, py in _flatten(m.group(1)):
            xs.append(px)
            ys.append(py)
    for m in re.finditer(r'\bpoints="([^"]+)"', body):
        nums = [float(v) for v in re.findall(NUM, m.group(1))]
        xs += nums[0::2]
        ys += nums[1::2]
    if not xs or not ys:
        raise IconError(
            "nothing is drawn once the text is removed. Every stage in this "
            "figure is text only, so there is no shape for an icon to be. "
            "Give it glyphs, or draw boxes with layout.chrome.")
    return min(xs) + ox, min(ys) + oy, max(xs) + ox, max(ys) + oy


def iconify(svg: str, width: float, height: float) -> str:
    """A rendered figure, reduced to what reads at *width* x *height*."""
    out = re.sub(r"<text\b.*?</text>", "", svg, flags=re.S)
    out = re.sub(r'<g class="ds-legend">.*?</g>', "", out, flags=re.S)
    for cls in SUBPIXEL_CLASSES:
        out = re.sub(r'<rect class="%s"[^>]*/>' % re.escape(cls), "", out)

    # A STAGE THAT DRAWS NOTHING TAKES ITS ARROWS WITH IT. Under
    # `layout.chrome: "none"` a stage without a glyph is text and nothing else,
    # so once the text goes its group is empty -- and the edges into and out of
    # it survive as arrows pointing at blank space.
    empty: set[str] = set()
    for g in re.finditer(
            r'<g class="ds-stage[^"]*" data-stage="([^"]*)"[^>]*>(.*?)</g>',
            out, re.S):
        if not _DRAWN.search(g.group(2)):
            empty.add(g.group(1))
            out = out.replace(g.group(0), "")
    for e in re.finditer(r'<path class="ds-edge[^"]*"[^>]*>', out):
        a = e.group(0)
        frm = re.search(r'data-from="([^"]*)"', a)
        to = re.search(r'data-to="([^"]*)"', a)
        if (frm and frm.group(1) in empty) or (to and to.group(1) in empty):
            out = out.replace(a, "")

    x1, y1, x2, y2 = _drawn_bounds(out)
    bw, bh = x2 - x1, y2 - y1
    pad = max(bw, bh) * MARGIN
    x1, y1, bw, bh = x1 - pad, y1 - pad, bw + 2 * pad, bh + 2 * pad

    root = re.search(r"<svg[^>]*>", out).group(0)
    new = re.sub(r'viewBox="[^"]*"',
                 f'viewBox="{x1:.2f} {y1:.2f} {bw:.2f} {bh:.2f}"', root)
    new = re.sub(r'\s+width="[^"]*"', "", new)
    new = re.sub(r'\s+height="[^"]*"', "", new)
    # `meet` rather than `slice`: an icon may letterbox, but it may never crop.
    # A cropped net is a net with a stage missing, which is a false figure at any
    # size.
    new = new.replace("<svg ", f'<svg width="{width:g}" height="{height:g}" '
                               'preserveAspectRatio="xMidYMid meet" ', 1)
    return out.replace(root, new, 1)


def scale_of(svg: str, width: float, height: float) -> float:
    """What `iconify`'s output renders at in a *width* x *height* slot."""
    m = re.search(r'viewBox="%s %s (%s) (%s)"' % (NUM, NUM, NUM, NUM), svg)
    bw, bh = float(m.group(1)), float(m.group(2))
    return min(width / bw, height / bh)


def render_icon(doc: dict, graph, width: float, height: float):
    """Render *doc* as an icon for a *width* x *height* slot.

    Returns (svg, layout_name, scale).

    THE COMMITTED LAYOUT IS A PAGE-FITTING DECISION AND AN ICON IS NOT ON THAT
    PAGE. `layout.wrap` exists to fold a figure into a column: lenet is wrapped
    to 600 units and comes out 470 x 593, which is taller than it is wide. Feed
    that to a 420 x 104 slot and it lands at 0.14x -- a mark with nothing in it --
    while the same net unwrapped is 5.9:1 and lands at 0.86x.

    So both layouts are rendered and the one that comes out LARGER in the slot
    wins. Measured rather than assumed, because which one wins depends on the
    slot: a tall tile would take the wrapped form, and this picks that without
    being told. The chosen name is returned so the caller can say which it used
    rather than leaving the reader to wonder why the icon does not match the
    figure.

    That name is `"as committed"`, `"unwrapped"`, or `"single"` -- the last
    meaning the two candidates came out identical and nothing was chosen. See
    the comment at the pick.
    """
    import copy

    from draughtsman.render import render
    from draughtsman.spec import load

    unwrapped = copy.deepcopy(doc)
    lay = unwrapped.setdefault("layout", {})
    lay["wrap"] = 10 ** 6            # effectively: do not wrap
    lay["legend"] = False            # a legend is prose and there is no text here

    drawn = []
    for name, candidate in (("as committed", doc), ("unwrapped", unwrapped)):
        try:
            svg = iconify(render(load(candidate), graph), width, height)
        except IconError:
            continue
        drawn.append((svg, name, scale_of(svg, width, height)))
    if not drawn:
        raise IconError(
            "no layout of this figure leaves anything drawable once the text is "
            "removed")

    # A CHOOSER THAT CANNOT SAY IT HAD NOTHING TO CHOOSE BETWEEN IS REPORTING A
    # DECISION IT DID NOT MAKE. `vae`, `unet` and `whisper` state no
    # `output.width`, so `width_budget` returns None, the automatic fold in
    # `render` never fires, and setting `wrap` to a number no figure reaches
    # changes nothing: both candidates come out BYTE-IDENTICAL. The old code
    # kept the first on a strict `>` and announced "as committed layout", which
    # reads as the committed form having won something. It won nothing; there
    # was one drawing wearing two names.
    #
    # This matters more than the wording. A reader who sees a layout named
    # believes the alternative was tried and was worse, and stops looking for
    # the reason their mark is unreadable -- when the reason may be that no
    # alternative was ever available to try.
    if len({svg for svg, _, _ in drawn}) == 1:
        svg, _, s = drawn[0]
        return svg, "single", s
    return max(drawn, key=lambda c: c[2])
