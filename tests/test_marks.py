"""Countable glyphs — a tensor drawn as objects rather than as an area.

The block glyph answers "bigger or smaller than that one". Marks answer "how
many", and that is a stronger claim: a reader can be wrong about an area and
never know, but a miscounted row of marks is wrong in a way they can check. So
the claim has a limit, and the limit is enforced rather than trusted — an axis
past counting is drawn as a bar with its number, never as marks nobody could
count.
"""

import copy
import json
import re

import pytest

from draughtsman.facts import Graph
from draughtsman.render import MARK_MAX, _Marks, render
from draughtsman.spec import Glyph, dump, load

MARK = re.compile(r'class="ds-mark"')
BAR = re.compile(r'class="ds-mark-bar"')
COUNT = re.compile(r'class="ds-mark-count"[^>]*>([^<]*)<')


#: `axes` INDEXES THE SHAPE AS DRAWN, not the traced one. tube declares
#: `batch_axis: 0`, so `{stage.out_shape}` presents (cells, frames) and the axes
#: naming them are 0 and 1 -- asking for 2 is an error naming the rank. A
#: `weight_shape` is different and the test above uses [0, 1] for its own
#: reason: a conv weight is (out_ch, in_ch, k) with no batch axis to hide, so
#: `drop_batch` never touches it. One numbering per spec, and it is the one the
#: reader sees; see DECISIONS.md correction 6.
def _with_glyph(doc, stage_id, **glyph):
    doc = copy.deepcopy(doc)
    # `tube` now carries glyphs of its own, and these tests use its spec as a
    # blank canvas. A test that builds a scenario on a committed spec has to
    # neutralise what it does not control, or it fails the day the corpus gains
    # a feature -- which is what happened here.
    for s in doc["stages"]:
        s.pop("glyph", None)
    stage = next(s for s in doc["stages"] if s["id"] == stage_id)
    stage["glyph"] = {"labels": ["rows", "cols"], "style": "marks", **glyph}
    return doc


# -- geometry ---------------------------------------------------------------

def test_two_countable_axes_make_a_grid():
    mk = _Marks((3, 5), ["rows", "cols"])
    assert mk.rows_ok and mk.cols_ok
    assert mk.bars == []
    assert mk.grid_w == 5 * 3.2 or mk.grid_w > 0     # cols wide, rows tall
    assert mk.grid_h > mk.grid_w / 2                 # 3 rows, 5 cols


def test_one_countable_axis_draws_a_column_and_a_bar():
    """Tony's case: 30 elements arranged vertically, 600 written underneath."""
    mk = _Marks((30, 600), ["cells", "frames"])
    assert mk.rows_ok and not mk.cols_ok
    assert mk.bars == [(1, 600)]


def test_the_limit_is_enforced_at_the_boundary():
    assert _Marks((MARK_MAX, 2), ["a", "b"]).rows_ok
    assert not _Marks((MARK_MAX + 1, 2), ["a", "b"]).rows_ok


def test_both_axes_past_counting_are_two_bars():
    mk = _Marks((900, 600), ["a", "b"])
    assert mk.bars == [(0, 900), (1, 600)]
    assert mk.h == pytest.approx(11.0 * 2)


def test_an_axis_of_zero_is_not_drawn_as_marks():
    """A traced shape can carry a zero-length axis. Zero marks would be
    indistinguishable from an axis that was never drawn."""
    assert not _Marks((0, 5), ["a", "b"]).rows_ok


# -- rendering --------------------------------------------------------------

def test_a_small_shape_draws_one_mark_per_element(tube_graph, tube_spec_doc):
    """8 filters x 5 inputs is forty marks, and forty is what gets drawn — the
    grid is never squeezed to fit, because the count IS the claim."""
    doc = _with_glyph(tube_spec_doc, "head", of="{node:n0149.weight_shape}",
                      axes=[0, 1], labels=["filters", "inputs"])
    svg = render(load(doc), tube_graph)
    assert len(MARK.findall(svg)) == 8 * 5
    assert BAR.findall(svg) == []


def test_a_large_axis_becomes_a_bar_with_its_number(tube_graph, tube_spec_doc):
    doc = _with_glyph(tube_spec_doc, "raster", of="{stage.out_shape}",
                      axes=[0, 1], labels=["cells", "frames"])
    svg = render(load(doc), tube_graph)
    assert len(MARK.findall(svg)) == 30        # the countable axis, drawn
    assert len(BAR.findall(svg)) == 1          # the frame axis, not drawn
    assert COUNT.findall(svg) == ["600"]       # ... but counted


def test_the_count_beside_the_bar_is_the_graph_s_number(tube_graph,
                                                        tube_spec_doc):
    """It is a fact like every other number in a figure, not a label."""
    doc = _with_glyph(tube_spec_doc, "raster", of="{stage.out_shape}",
                      axes=[0, 1], labels=["cells", "frames"])
    svg = render(load(doc), tube_graph)
    assert tube_graph.nodes["in1"]["out_shape"] == [1, 30, 600]
    assert COUNT.findall(svg) == ["600"]


def test_the_legend_states_the_claim_and_its_limit(tube_graph, tube_spec_doc):
    """A bar a reader is not told about reads as an axis of one."""
    doc = _with_glyph(tube_spec_doc, "raster", of="{stage.out_shape}",
                      axes=[0, 1], labels=["cells", "frames"])
    doc["layout"] = {"legend": True}
    svg = render(load(doc), tube_graph)
    assert "one mark = one cell" in svg
    assert f"more than {MARK_MAX}" in svg
    assert "∝" not in svg                      # not the block's scale note


def test_the_box_grows_for_its_marks(tube_graph, tube_spec_doc):
    """Marks are drawn at a fixed pitch and the box widens to hold them. The
    alternative — scaling the grid into the box it was given — would make two
    stages with different counts draw the same picture."""
    import copy
    bare = copy.deepcopy(tube_spec_doc)
    for st in bare["stages"]:
        st.pop("glyph", None)
    plain = render(load(bare), tube_graph)
    marked = render(load(_with_glyph(tube_spec_doc, "raster",
                                     of="{stage.out_shape}", axes=[0, 1],
                                     labels=["cells", "frames"])), tube_graph)
    def height(svg):
        return float(re.search(r'viewBox="0 0 [\d.]+ ([\d.]+)"', svg)[1])
    assert height(marked) > height(plain)


# -- the spec side ----------------------------------------------------------

def test_style_round_trips_and_block_stays_the_default(tube_spec):
    spec = copy.deepcopy(tube_spec)
    spec.stages[0].glyph = Glyph(of="{stage.out_shape}", axes=[0, 1],
                                 labels=["a", "b"], style="marks")
    assert load(dump(spec)).stages[0].glyph.style == "marks"

    spec.stages[0].glyph = Glyph(of="{stage.out_shape}", axes=[0, 1],
                                 labels=["a", "b"])
    assert "style" not in dump(spec)["stages"][0]["glyph"]
    assert load(dump(spec)).stages[0].glyph.style == "block"


def test_the_payload_documents_the_style_and_not_just_the_word(tube_graph):
    """`Glyph.style` shares a name with `Edge.style`, so the field-coverage test
    in test_payload.py passes on it whether or not it is documented — a real hole
    in that test, named here rather than left to be discovered. This asserts the
    glyph's own spelling and the reason a reader would choose it."""
    from draughtsman.abstract import payload
    text = payload(tube_graph)
    assert '"style": "block|marks"' in text
    assert "HOW MANY" in text
    assert "Counting stops working" in text
