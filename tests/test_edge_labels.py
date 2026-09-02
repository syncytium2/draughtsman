"""Edge labels — the gap the gallery left standing.

    "An edge label collided with a stage box. Whisper's audio-features edge
     crosses a rank boundary and its label was drawn under the cross-attention
     box that starts there. Worked around by dropping a label the stage name
     already carried, but edge labels have no collision handling at all."
                                            — examples/gallery/README.md

The workaround cost that figure a label. This is the fix and the assertion that
keeps it fixed.
"""

import re

import pytest

from conftest import EXAMPLES, IDS
from draughtsman.render import (_along, _label_rect, _overlaps,
                                _place_label)
from draughtsman.text import width

EDGE_LABEL_SIZE = 9.0

STAGE_RE = re.compile(r'<g class="ds-stage.*?</g>', re.S)
RECT_RE = re.compile(r'<rect x="([-\d.]+)" y="([-\d.]+)" '
                     r'width="([\d.]+)" height="([\d.]+)"')
LABEL_RE = re.compile(r'<text class="ds-edge-label" x="([-\d.]+)" '
                      r'y="([-\d.]+)"[^>]*>(.*?)</text>')


def _boxes(svg: str):
    out = []
    for group in STAGE_RE.findall(svg):
        m = RECT_RE.search(group)          # the stage's own rect comes first
        if m:
            x, y, w, h = (float(v) for v in m.groups())
            out.append((x, y, x + w, y + h))
    return out


def _labels(svg: str):
    out = []
    for x, y, text in LABEL_RE.findall(svg):
        out.append((text, _label_rect(float(x), float(y),
                                      width(text, EDGE_LABEL_SIZE))))
    return out


# -- the unit that was wrong -------------------------------------------------

def test_the_midpoint_of_a_two_point_edge_is_not_its_endpoint():
    """THE BUG, IN ONE ASSERTION. The old code took `points[len(points) // 2]`,
    which for a two-point edge is index 1 — the destination's entry point. Every
    short labelled edge drew its label centred on the box it pointed at."""
    pts = [(0.0, 0.0), (100.0, 0.0)]
    assert pts[len(pts) // 2] == (100.0, 0.0)      # what it used to do
    assert _along(pts, 0.5) == (50.0, 0.0)         # what it does now


def test_along_measures_by_length_not_by_vertex_count():
    """A polyline with a long first leg and short later ones: the halfway point
    is in the long leg, not at the second vertex."""
    pts = [(0.0, 0.0), (90.0, 0.0), (95.0, 0.0), (100.0, 0.0)]
    x, y = _along(pts, 0.5)
    assert (round(x), round(y)) == (50, 0)


@pytest.mark.parametrize("t,expected", [(0.0, 0.0), (0.25, 25.0), (1.0, 100.0)])
def test_along_spans_the_whole_path(t, expected):
    pts = [(0.0, 0.0), (40.0, 0.0), (100.0, 0.0)]
    assert round(_along(pts, t)[0], 6) == expected


def test_overlaps_is_exclusive_at_the_edges():
    a = (0.0, 0.0, 10.0, 10.0)
    assert _overlaps(a, (5.0, 5.0, 15.0, 15.0))
    assert not _overlaps(a, (10.0, 0.0, 20.0, 10.0))    # touching is not overlap
    assert not _overlaps(a, (0.0, 10.0, 10.0, 20.0))


# -- the collision itself ----------------------------------------------------
#
# THESE ARE THE TESTS WITH TEETH, and it is worth saying why the ones below them
# are not. Running the old placement rule against all eleven committed figures
# produces ZERO collisions: the workaround had already deleted the one label that
# collided, and every surviving labelled edge spans two ranks, where
# `points[len // 2]` happens to land on the dummy in the middle. So the sweep
# below would have passed on the day the bug was reported. It is worth keeping —
# it is the property one actually wants — but it discriminates nothing on today's
# corpus, and these do.

def test_a_label_on_a_short_edge_clears_the_box_it_points_at():
    """The reported case: an edge between adjacent ranks has two points, so the
    old rule put its label on the destination's entry — inside the box."""
    pts = [(100.0, 50.0), (200.0, 50.0)]
    box = (200.0, 26.0, 320.0, 74.0)          # the destination, starting at 200
    text = "audio features"

    old = _label_rect(pts[len(pts) // 2][0], pts[len(pts) // 2][1] - 5,
                      width(text, EDGE_LABEL_SIZE))
    assert _overlaps(old, box), "the old rule should land on the box"

    x, y = _place_label(pts, text, False, [box])
    assert not _overlaps(_label_rect(x, y, width(text, EDGE_LABEL_SIZE)), box)


def test_a_label_steps_aside_for_something_already_placed():
    pts = [(0.0, 50.0), (200.0, 50.0)]
    occupied = []
    first = _place_label(pts, "one", False, occupied)
    second = _place_label(pts, "two", False, occupied)
    assert first != second
    assert not _overlaps(_label_rect(*first, width("one", EDGE_LABEL_SIZE)),
                         _label_rect(*second, width("two", EDGE_LABEL_SIZE)))


def test_a_label_with_nowhere_to_go_is_still_drawn():
    """Boxed in on every candidate, it returns the least bad spot rather than
    nothing. The workaround for this bug had to delete a label; the fix must not
    institutionalise that."""
    pts = [(0.0, 50.0), (200.0, 50.0)]
    everywhere = [(-500.0, -500.0, 500.0, 500.0)]
    x, y = _place_label(pts, "hemmed in", False, everywhere)
    assert 0.0 <= x <= 200.0


def test_a_vertical_figure_moves_the_label_sideways():
    """Nudging it up in a top-to-bottom figure moves it along the edge, not off
    it, so the offset has to follow the orientation."""
    pts = [(50.0, 0.0), (50.0, 200.0)]
    box = (26.0, 200.0, 74.0, 320.0)
    x, y = _place_label(pts, "skip", True, [box])
    assert abs(x - 50.0) > 1.0, "the label did not move off the spine"


# -- the property, over everything committed ---------------------------------

@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_no_edge_label_lands_on_a_stage_box(d):
    svg = (d / "figure.svg").read_text()
    boxes = _boxes(svg)
    assert boxes, "parsed no stage boxes — the assertion would be vacuous"
    for text, rect in _labels(svg):
        hits = [b for b in boxes if _overlaps(rect, b)]
        assert not hits, f"edge label {text!r} overlaps {len(hits)} stage box(es)"


@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_no_two_edge_labels_land_on_each_other(d):
    labels = _labels((d / "figure.svg").read_text())
    for i, (text_a, a) in enumerate(labels):
        for text_b, b in labels[i + 1:]:
            assert not _overlaps(a, b), f"{text_a!r} overlaps {text_b!r}"


def test_the_figures_still_carry_their_labels(example_dir):
    """The old workaround was to delete the label. A collision fix that quietly
    stopped drawing them would pass every assertion above."""
    svg = (example_dir / "figure.svg").read_text()
    assert [t for t, _ in _labels(svg)] == ["bypass"]
