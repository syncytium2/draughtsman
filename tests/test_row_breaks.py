"""Named row breaks — the spec says where a row starts, not only how wide it may be.

`layout.wrap` gives the packer a width and lets it choose the cuts. bugarach's
four comparison models needed the cut itself to mean something: every figure's
first row is the stages that still hold one row per ROI, so the length of that
row is the comparison. `line_length`'s even re-pack moved its vote to the second
row at every wrap from 480 to 680. `layout.breaks` names the cuts instead.
"""

import copy

import pytest

from draughtsman.check import check
from draughtsman.layout import build
from draughtsman.render import render
from draughtsman.spec import dump, load


def _chain(n, w=120.0, h=48.0):
    ids = [f"s{i}" for i in range(n)]
    nodes = [(i, w, h) for i in ids]
    edges = [(a, b, None, "solid") for a, b in zip(ids, ids[1:])]
    return nodes, edges


def _rows_of(drawing):
    """Stage ids grouped by the row they were placed on, top row first."""
    rows = {}
    for b in drawing.boxes.values():
        if not b.dummy:
            rows.setdefault(round(b.y, 1), []).append(b)
    return [[b.id for b in sorted(v, key=lambda b: b.x)]
            for _, v in sorted(rows.items())]


def test_rows_start_exactly_at_the_named_stages():
    nodes, edges = _chain(8)
    d = build(nodes, edges, breaks=["s3", "s6"])
    assert d.rows == 3
    assert _rows_of(d) == [["s0", "s1", "s2"], ["s3", "s4", "s5"], ["s6", "s7"]]


def test_named_breaks_are_not_re_packed_to_an_even_share():
    """The case wrap cannot express: a short first row before long later ones.
    An even re-pack of this chain would move s2 down; the names keep it up."""
    nodes, edges = _chain(8)
    d = build(nodes, edges, breaks=["s3"])
    assert _rows_of(d)[0] == ["s0", "s1", "s2"]


def test_no_breaks_is_the_figure_it_always_was():
    nodes, edges = _chain(8)
    assert build(nodes, edges, wrap=400).width == build(nodes, edges, wrap=400,
                                                         breaks=()).width


@pytest.mark.parametrize("cut", ["s2", "s3"])
def test_a_named_break_never_cuts_an_edge_in_flight(cut):
    """The packer's own rule, applied to a cut a person chose: s1 -> s3 skips s2,
    so a row may not start at s2 or at s3."""
    nodes, edges = _chain(5)
    edges.append(("s1", "s3", None, "solid"))
    with pytest.raises(ValueError, match="in flight"):
        build(nodes, edges, breaks=[cut])


def test_a_break_after_the_skip_has_landed_is_legal():
    nodes, edges = _chain(5)
    edges.append(("s1", "s3", None, "solid"))
    assert build(nodes, edges, breaks=["s4"]).rows == 2


def test_a_break_at_the_first_stage_is_refused():
    nodes, edges = _chain(3)
    with pytest.raises(ValueError, match="first rank"):
        build(nodes, edges, breaks=["s0"])


def _tube_with(tube_spec_doc, **layout):
    doc = copy.deepcopy(tube_spec_doc)
    doc["layout"] = {k: v for k, v in {**doc["layout"], **layout}.items()
                     if v is not None}
    return doc


def test_check_passes_a_legal_break_and_render_honours_it(tube_spec_doc, tube_graph):
    """tube's bypass leaves the mean and rejoins at the concat, so a row may start
    AT the mean — the collapse — and not at the kernel bank."""
    doc = _tube_with(tube_spec_doc, wrap=None, breaks=["mean"])
    result = check(load(doc), tube_graph)
    assert result.ok, result.errors
    svg = render(load(doc), tube_graph)
    assert svg.count("<svg") == 1


def test_check_refuses_a_break_inside_the_bypass(tube_spec_doc, tube_graph):
    doc = _tube_with(tube_spec_doc, wrap=None, breaks=["dog"])
    result = check(load(doc), tube_graph)
    assert not result.ok
    assert any("in flight" in e for e in result.errors)


def test_check_refuses_a_break_that_names_no_stage(tube_spec_doc, tube_graph):
    doc = _tube_with(tube_spec_doc, wrap=None, breaks=["nowhere"])
    result = check(load(doc), tube_graph)
    assert any("'nowhere', which is not a stage" in e for e in result.errors)


def test_check_refuses_breaks_beside_a_wrap(tube_spec_doc, tube_graph):
    """Two answers to one question, and the figure would draw only one of them."""
    doc = _tube_with(tube_spec_doc, wrap=600, breaks=["mean"])
    result = check(load(doc), tube_graph)
    assert any("both set" in e for e in result.errors)


def test_breaks_survive_a_round_trip_and_are_absent_when_unset(tube_spec_doc):
    doc = _tube_with(tube_spec_doc, wrap=None, breaks=["mean", "head"])
    assert dump(load(doc))["layout"]["breaks"] == ["mean", "head"]
    assert "breaks" not in dump(load(tube_spec_doc))["layout"]
