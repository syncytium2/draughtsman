"""Row wrapping and orientation — the answer to the strip.

The gallery measured lenet 8.1:1, resnet 8.1:1, transformer 7.8:1. SPEC.md §2
condemned torchview for a strip; those are the same defect arrived at more
slowly, and no coverage check catches them because nothing is wrong with them
except the shape.
"""

import copy
import json

import pytest

from conftest import EXAMPLES, IDS
from draughtsman.facts import Graph
from draughtsman.layout import build
from draughtsman.render import render
from draughtsman.spec import Layout, dump, length_pt, load


def _chain(n, w=120.0, h=48.0):
    ids = [f"s{i}" for i in range(n)]
    nodes = [(i, w, h) for i in ids]
    edges = [(a, b, None, "solid") for a, b in zip(ids, ids[1:])]
    return nodes, edges


def test_no_wrap_is_one_row():
    nodes, edges = _chain(8)
    d = build(nodes, edges)
    assert d.rows == 1
    ys = [b.y for b in d.boxes.values()]
    assert max(ys) - min(ys) < 0.5


def test_wrapping_trades_width_for_height():
    nodes, edges = _chain(8)
    wide, wrapped = build(nodes, edges), build(nodes, edges, wrap=400)
    assert wrapped.rows > 1
    assert wrapped.width < wide.width
    assert wrapped.height > wide.height
    assert wrapped.width / wrapped.height < wide.width / wide.height


def test_rows_are_balanced_rather_than_greedy():
    """Greedy packing fills each row to the brim and leaves a widow alone on the
    last one. Nine equal boxes should not come out 4/4/1."""
    nodes, edges = _chain(9)
    d = build(nodes, edges, wrap=500)
    rows = {}
    for b in d.boxes.values():
        rows.setdefault(round(b.y, 1), []).append(b)
    counts = sorted(len(v) for v in rows.values())
    assert counts[-1] - counts[0] <= 1, f"rows are ragged: {counts}"


def test_a_row_break_never_cuts_an_edge_in_flight():
    """U-Net's skips span the whole depth, so it cannot wrap — and that is the
    honest answer. Cutting a skip across a break would not fix the shape, it
    would hide where the edge went."""
    nodes, edges = _chain(8)
    edges.append(("s0", "s7", "skip", "dashed"))     # spans everything
    d = build(nodes, edges, wrap=300)
    assert d.rows == 1, "wrapped through an edge that was still in flight"


def test_wrap_connectors_are_marked_so_they_can_be_drawn_differently():
    nodes, edges = _chain(8)
    d = build(nodes, edges, wrap=400)
    wrapped = [r for r in d.routes if r.wrapped]
    assert len(wrapped) == d.rows - 1
    for r in wrapped:
        assert len(r.points) == 6          # out, right, gutter, left, in, entry


def test_vertical_is_the_same_layout_transposed():
    """Not "narrower and taller" — that would pass for any second engine. The
    claim is that `tb` IS `lr` with the axes swapped, so laying out boxes whose
    sizes are already swapped must reproduce it exactly.

    (The two drawings are not each other's transpose: the rank-axis gap applies
    to width going across and to height going down, so a chain of 120×48 boxes
    is not 1022×80 one way and 80×1022 the other.)
    """
    nodes, edges = _chain(6)
    across = build(nodes, edges)
    down = build(nodes, edges, orientation="tb")
    swapped = build([(i, h, w) for i, w, h in nodes], edges)

    assert down.vertical and not across.vertical
    assert round(down.width, 6) == round(swapped.height, 6)
    assert round(down.height, 6) == round(swapped.width, 6)
    for i, _, _ in nodes:
        a, b = down.boxes[i], swapped.boxes[i]
        assert (a.w, a.h) == (120.0, 48.0)     # real proportions, not swapped
        assert round(a.x + a.w / 2, 6) == round(b.y, 6)
        assert round(a.y - a.h / 2, 6) == round(b.x, 6)

    assert down.width < across.width and down.height > across.height


def test_vertical_flows_downward_in_declaration_order():
    nodes, edges = _chain(5)
    d = build(nodes, edges, orientation="tb")
    ys = [d.boxes[f"s{i}"].y for i in range(5)]
    assert ys == sorted(ys)
    xs = [d.boxes[f"s{i}"].x for i in range(5)]
    assert max(xs) - min(xs) < 0.5, "the column is not straight"


def test_an_unknown_orientation_is_refused():
    nodes, edges = _chain(3)
    with pytest.raises(ValueError, match="orientation"):
        build(nodes, edges, orientation="diagonal")


def test_nothing_is_placed_off_canvas_when_wrapped():
    nodes, edges = _chain(9)
    for kw in ({"wrap": 400}, {"orientation": "tb"},
               {"orientation": "tb", "wrap": 300}):
        d = build(nodes, edges, **kw)
        for b in d.boxes.values():
            assert 0 <= b.x and b.x + b.w <= d.width + 0.01, kw
            assert 0 <= b.y - b.h / 2 and b.y + b.h / 2 <= d.height + 0.01, kw


# -- the spec side ----------------------------------------------------------

def test_layout_defaults_are_omitted_from_the_spec(tube_spec):
    """Adding this field must change no existing spec and no existing figure.

    Asserted against a COPY with the layout reset, not against whatever
    `examples/tube` currently declares: this is an invariant of `dump`, and
    pinning it to one example's arrangement makes an unrelated spec edit look
    like a regression in the spec format. (It did — the legend landed and this
    went red.)
    """
    plain = copy.deepcopy(tube_spec)
    plain.layout = Layout()
    assert "layout" not in dump(plain)


def test_layout_round_trips(tube_spec):
    # A COPY. `tube_spec` is session-scoped, so assigning to it here leaked a
    # top-to-bottom wrapped layout into every test that ran afterwards and
    # asserted something about the committed figure.
    spec = copy.deepcopy(tube_spec)
    spec.layout = Layout(orientation="tb", wrap=760)
    again = load(dump(spec))
    assert again.layout.orientation == "tb"
    assert again.layout.wrap == 760


def test_the_legend_flag_round_trips(tube_spec):
    spec = copy.deepcopy(tube_spec)
    spec.layout = Layout(legend=True)
    assert load(dump(spec)).layout.legend is True
    spec.layout = Layout()
    assert load(dump(spec)).layout.legend is False


@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_every_model_renders_wrapped_and_vertical(d):
    """Ten architectures, three arrangements each. A layout that only holds for
    the shape it was developed on is not a layout."""
    graph = Graph(json.loads((d / "graph.json").read_text()))
    doc = json.loads((d / "spec.json").read_text())
    flat = render(load(doc), graph)
    for lay in ({"orientation": "lr", "wrap": 760}, {"orientation": "tb"},
                {"orientation": "tb", "wrap": 600}):
        variant = dict(doc, layout=lay)
        svg = render(load(variant), graph)
        assert svg.startswith("<svg")
        assert svg.count("ds-stage") == flat.count("ds-stage")


# --- fit to the page --------------------------------------------------------
#
#     "NO FIGURE IS LEGIBLE AT A JOURNAL COLUMN WIDTH ... A figure has to come in
#      at 399 units to clear 6pt in a column and the narrowest today is 646."
#                                            — CLAIMS.md, queue item 3
#
# A figure declared no physical size at all, so a page scaled it to fit and took
# the type down with it. `output.width` states where it is going; the budget the
# floor implies is what layout solves against.

import re as _re

from draughtsman.render import width_budget, type_pt


def _units(svg: str) -> float:
    return float(_re.search(r'viewBox="0 0 ([\d.]+)', svg).group(1))


@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_a_declared_output_size_is_what_the_svg_says(d):
    """The SVG must assert inches, not a pixel count.

    `width="1594.64"` is unitless and therefore pixels: the figure claims to be
    1594 pixels wide and every consumer scales it to whatever fits. `width="6in"`
    is the figure saying how big it is, which is the only form a page can honour.
    """
    spec = load(json.loads((d / "spec.json").read_text()))
    svg = (d / "figure.svg").read_text()
    root = _re.search(r"<svg[^>]*>", svg).group(0)
    declared = _re.search(r'width="([^"]+)"', root).group(1)
    if spec.output.width:
        assert declared == spec.output.width, (
            f"{d.name} declares output.width {spec.output.width!r} but the SVG "
            f"says width={declared!r}. A page cannot honour a size the figure "
            "does not state.")
        assert _re.search(r'height="[\d.]+in"', root), (
            f"{d.name}: width is physical but height is not, so the aspect is "
            "left to the consumer to guess")
    else:
        assert _re.fullmatch(r"[\d.]+", declared), (
            f"{d.name}: width={declared!r} is neither a bare unit count nor a "
            "declared physical size")


@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_a_figure_that_states_its_size_is_legible_at_it(d):
    """Type never gives. If it would, the figure is too wide and must narrow."""
    spec = load(json.loads((d / "spec.json").read_text()))
    if not spec.output.width:
        return                      # not a skip: nothing was promised
    units = _units((d / "figure.svg").read_text())
    got, budget = type_pt(spec, units), width_budget(spec)
    floor = length_pt(spec.output.min_type, "min_type")
    assert got >= floor, (
        f"{d.name} at {spec.output.width}: smallest type is {got:.2f}pt, under "
        f"the {spec.output.min_type} floor. {units:.0f} units against a budget "
        f"of {budget:.0f}. Narrow the figure — never the type.")
