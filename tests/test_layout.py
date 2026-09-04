"""SPEC.md §4 — coordinates derived from topology, once, for any graph.

The objection that started this repo is coordinates typed per figure, and the
concrete failure it produced was lane labels struck through by the figure's own
edges — invisible in the source, obvious in the render. These are the properties
that make that unable to happen.
"""

from draughtsman.layout import DUMMY_H, build


def _line(*ids):
    return [(a, b, None, "solid") for a, b in zip(ids, ids[1:])]


def test_ranks_follow_the_longest_path():
    d = build([(i, 60, 30) for i in "abcd"], _line("a", "b", "c", "d"))
    xs = [d.boxes[i].x for i in "abcd"]
    assert xs == sorted(xs)


def test_a_skipping_edge_gets_a_dummy_at_every_rank_it_crosses():
    """This is what reserves space for the bypass, before anything is drawn."""
    nodes = [(i, 60, 30) for i in "abcd"]
    edges = _line("a", "b", "c", "d") + [("a", "d", "bypass", "dashed")]
    d = build(nodes, edges)
    dummies = [b for b in d.boxes.values() if b.dummy]
    assert len(dummies) == 2                      # ranks 1 and 2
    assert all(b.h == DUMMY_H for b in dummies)
    bypass = next(r for r in d.routes if r.label == "bypass")
    # Exit, BOTH ENDS of each dummy, entry. A dummy is as wide as the rank it
    # crosses so the bypass runs level beneath that stage; one point per dummy was
    # the old shape and it is what let the curve bow up into the skipped box's
    # bottom corners on either side of it.
    assert len(bypass.points) == 6

    # THE COUNT IS NOT THE PROPERTY -- the flatness is, and a count passes just as
    # happily on two points at different heights. Each dummy's pair must share a y,
    # which is what makes the run between them level.
    interior = bypass.points[1:-1]
    pairs = list(zip(interior[::2], interior[1::2]))
    assert len(pairs) == 2
    for (x0, y0), (x1, y1) in pairs:
        assert x1 > x0, "the flat run has no width"
        assert abs(y1 - y0) < 1e-6, "the run beneath the skipped stage is not level"


def test_the_skipping_edge_does_not_run_through_the_boxes_it_skips():
    """The failure this replaces: an edge drawn over a label because nothing
    reserved the space."""
    nodes = [("a", 60, 30), ("b", 60, 80), ("c", 60, 30)]
    d = build(nodes, [("a", "b", None, "solid"), ("b", "c", None, "solid"),
                      ("a", "c", "bypass", "dashed")])
    b = d.boxes["b"]
    dummy = next(x for x in d.boxes.values() if x.dummy)
    assert abs(dummy.y - b.y) >= b.h / 2, "the bypass runs through the box it skips"


def test_the_main_chain_comes_out_straight():
    """Textbook Sugiyama would straighten the long edge and bend the chain. A
    reader follows the chain, so the weights here are the other way round."""
    nodes = [(i, 60, 30) for i in "abcd"]
    d = build(nodes, _line("a", "b", "c", "d") + [("a", "d", None, "dashed")])
    ys = [d.boxes[i].y for i in "abcd"]
    assert max(ys) - min(ys) < 0.5


def test_a_fork_that_rejoins_puts_the_branches_on_separate_lanes():
    nodes = [("in", 60, 30), ("l", 60, 30), ("r", 60, 30), ("out", 60, 30)]
    d = build(nodes, [("in", "l", None, "solid"), ("in", "r", None, "solid"),
                      ("l", "out", None, "solid"), ("r", "out", None, "solid")])
    assert d.boxes["l"].x == d.boxes["r"].x         # same rank
    assert abs(d.boxes["l"].y - d.boxes["r"].y) >= 30


def test_edge_declaration_order_sets_lane_order():
    """The one knob a human gets over vertical arrangement, and it is worth more
    than a better prompt (SPEC.md §8.3)."""
    nodes = [("in", 60, 30), ("l", 60, 30), ("r", 60, 30), ("out", 60, 30)]
    first = build(nodes, [("in", "l", None, "solid"), ("in", "r", None, "solid"),
                          ("l", "out", None, "solid"), ("r", "out", None, "solid")])
    second = build(nodes, [("in", "r", None, "solid"), ("in", "l", None, "solid"),
                           ("r", "out", None, "solid"), ("l", "out", None, "solid")])
    assert (first.boxes["l"].y < first.boxes["r"].y) is not \
           (second.boxes["l"].y < second.boxes["r"].y)


def test_layout_is_identical_run_to_run():
    nodes = [(i, 60, 30) for i in "abcdef"]
    edges = _line(*"abcdef") + [("a", "d", None, "dashed"), ("b", "f", None, "solid")]
    one, two = build(nodes, edges), build(nodes, edges)
    assert {k: (v.x, v.y) for k, v in one.boxes.items()} == \
           {k: (v.x, v.y) for k, v in two.boxes.items()}


def test_nothing_is_placed_off_canvas():
    nodes = [(i, 60, 30) for i in "abcd"]
    d = build(nodes, _line("a", "b", "c", "d") + [("a", "d", None, "dashed")])
    for b in d.boxes.values():
        assert 0 <= b.x and b.x + b.w <= d.width
        assert 0 <= b.y - b.h / 2 and b.y + b.h / 2 <= d.height
