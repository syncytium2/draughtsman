"""An icon is the figure with everything unreadable removed.

`check` refuses a figure whose type would print under its floor. It has nothing
to say about a card or a tile, where no type survives at any size: at 420x104
every figure in this gallery lands between 1.6px and 3.6px of body type. The
answer there is not a smaller floor but no text, which is Tony's rule and the
reason tonydefazio.com's draughtsman card carries a hand-drawn schematic rather
than draughtsman's own output.

EVERY ASSERTION HERE IS A DEFECT THAT SHIPPED IN A HAND-BUILT ICON, and all of
them were found by rasterising the output and looking at it rather than by
measuring it. That is worth stating in the file that now checks them, because the
measurements were all green while the pictures were wrong.
"""

from __future__ import annotations

import json
import re

import pytest

from conftest import EXAMPLES, IDS
from draughtsman.facts import Graph
from draughtsman.icon import (IconError, _body_offset, _drawn_bounds, iconify,
                              parse_size, render_icon, scale_of)
from draughtsman.render import render
from draughtsman.spec import load

SLOT = (420.0, 104.0)
NUM = r"-?\d+\.?\d*"


def _icon(d, w=SLOT[0], h=SLOT[1]):
    doc = json.loads((d / "spec.json").read_text())
    graph = Graph(json.loads((d / "graph.json").read_text()))
    return render_icon(doc, graph, w, h)


@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_an_icon_carries_no_text_at_all(d):
    """The point of the mode. Labels at 1.8px are grey noise that reads as
    damage to the drawing rather than as writing."""
    svg, _, _ = _icon(d)
    assert "<text" not in svg, f"{d.name}'s icon still carries text"


@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_no_arrow_points_at_nothing(d):
    """A STAGE THAT DRAWS ONLY TEXT BECOMES AN EMPTY GROUP WHEN THE TEXT GOES,
    and its edges survive. lenet's icon ended with three arrows trailing off the
    right into blank space -- five stages there draw text and nothing else under
    `layout.chrome: "none"`.

    So every edge in an icon must still name two stages the icon draws.
    """
    svg, _, _ = _icon(d)
    drawn = set(re.findall(r'<g class="ds-stage[^"]*" data-stage="([^"]*)"', svg))
    for m in re.finditer(r'<path class="ds-edge[^"]*"([^>]*)>', svg):
        a = m.group(1)
        frm = re.search(r'data-from="([^"]*)"', a)
        to = re.search(r'data-to="([^"]*)"', a)
        for end in (frm, to):
            if end:
                assert end.group(1) in drawn, (
                    f"{d.name}'s icon draws an edge to {end.group(1)!r}, which "
                    "is not in the icon: an arrow pointing at nothing")


@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_the_whole_drawing_is_inside_the_frame(d):
    """THE ONE THAT WOULD HAVE CAUGHT THE TRANSFORM BUG.

    Everything is drawn inside `<g class="ds-body" transform="translate(0 N)">`,
    and the first version of `_drawn_bounds` measured in that group's space and
    wrote the viewBox in the root's. The result is a legal rectangle of exactly
    the right size in the wrong place, so the icon renders and is quietly clipped
    along one edge -- by 22 units for a figure with no caption and 36 with one,
    which is a spec field this code never reads.

    Two icons with identical viewBoxes and identical element counts did not look
    the same, and that is the only way it was noticed. This asserts the thing the
    eye was checking: every drawn point lies within the frame.
    """
    svg, _, _ = _icon(d)
    m = re.search(r'viewBox="(%s) (%s) (%s) (%s)"' % ((NUM,) * 4), svg)
    vx, vy, vw, vh = (float(m.group(i)) for i in range(1, 5))
    x1, y1, x2, y2 = _drawn_bounds(svg)
    slack = 0.01
    assert x1 >= vx - slack and x2 <= vx + vw + slack, (
        f"{d.name}'s icon is clipped horizontally: drawing spans "
        f"[{x1:.1f}, {x2:.1f}], frame is [{vx:.1f}, {vx + vw:.1f}]")
    assert y1 >= vy - slack and y2 <= vy + vh + slack, (
        f"{d.name}'s icon is clipped vertically: drawing spans "
        f"[{y1:.1f}, {y2:.1f}], frame is [{vy:.1f}, {vy + vh:.1f}]. This is the "
        "ds-body transform being measured in one space and cropped in another.")


def test_the_body_transform_is_actually_being_read():
    """A guard on the guard. If `ds-body` stops carrying a translate, or carries
    it in a form this regex misses, `_body_offset` silently returns (0, 0) and
    the test above passes because both measurements are wrong together."""
    d = next(p for p in EXAMPLES if p.name == "lenet")
    spec = load(json.loads((d / "spec.json").read_text()))
    graph = Graph(json.loads((d / "graph.json").read_text()))
    svg = render(spec, graph)
    assert 'class="ds-body"' in svg
    _, oy = _body_offset(svg)
    assert oy > 0, (
        "the ds-body transform reads as zero. If the renderer stopped "
        "translating the body this is fine and the offset can go; if the "
        "transform merely changed shape, every icon is being cropped again.")


@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_an_icon_is_never_cropped_to_fill_its_slot(d):
    """`meet`, never `slice`. An icon may letterbox; it may not lose a stage.
    A cropped net is a net with something missing, which is a false figure at any
    size -- and at icon size nobody can tell."""
    svg, _, _ = _icon(d)
    assert 'preserveAspectRatio="xMidYMid meet"' in svg, d.name


def test_the_layout_is_chosen_by_what_fits_not_by_what_is_committed():
    """`layout.wrap` is a page-fitting decision and an icon is not on that page.

    lenet is wrapped to 600 units and renders 470 x 593 -- taller than it is
    wide. In a 420 x 104 slot that lands at 0.14x, a mark with nothing in it,
    while the same net unwrapped is 5.9:1 and lands at 0.86x. So both are
    rendered and the larger wins.
    """
    d = next(p for p in EXAMPLES if p.name == "lenet")
    svg, chosen, scale = _icon(d)
    assert chosen == "unwrapped", chosen
    assert scale > 0.5, f"lenet's icon lands at {scale:.2f}x, which is the "\
                        "committed layout winning when it should not"

    # and the choice must be made by measurement, not hardcoded: a tall slot
    # takes the other one.
    _, tall_choice, _ = _icon(d, 104.0, 420.0)
    assert tall_choice == "as committed", (
        "a tall slot still chose the unwrapped layout, so the pick is not "
        f"being measured: got {tall_choice!r}")


def test_a_size_that_is_not_a_size_is_refused():
    for bad in ("420", "", "420x", "x104", "0x104", "-4x10", "wide"):
        with pytest.raises(IconError):
            parse_size(bad)
    assert parse_size("420x104") == (420.0, 104.0)
    assert parse_size(" 64 X 64 ") == (64.0, 64.0)


def test_a_figure_with_nothing_drawable_says_so_rather_than_emitting_a_blank():
    """An empty SVG is a file that looks like it worked. The failure has to be
    louder than the success."""
    blank = ('<svg viewBox="0 0 10 10"><g class="ds-body" transform="translate(0 0)">'
             '<g class="ds-stage ds-kind-op" data-stage="a">'
             '<text x="1" y="1">only text</text></g></g></svg>')
    with pytest.raises(IconError, match="nothing is drawn"):
        iconify(blank, *SLOT)


@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_an_icon_still_draws_something(d):
    """Every model in the gallery must survive the mode. A figure reduced to
    nothing is not an icon, and finding out per-model is the point of the sweep."""
    svg, _, scale = _icon(d)
    assert re.search(r"<(rect|path|polygon)\b", svg), f"{d.name}'s icon is empty"
    assert scale > 0, d.name
    assert scale_of(svg, *SLOT) == pytest.approx(scale)
