"""CLAIMS.md queue item 11 — the tube drawn for bugarach's front-page slot.

bugarach's landing page inlines the tube figure in a box measured, on 2026-09-10,
at **1203 px on a 1280 laptop and 395 px on a phone**. The page never shrinks the
figure below its viewBox width; it scrolls instead. So a figure wider than its
slot by one unit is a figure the reader drags sideways, and the gallery tube
(933.69 on two rows) and the figure the page carried (1247.87 on one) both miss.

Two specs sit beside `spec.json`, one per slot, each stating its slot as
`output.width` and DETAIL_SIZE in px as `output.min_type`. That pair makes the
unit budget exactly the slot width, so `check` refuses anything that would have
to be scaled down to fit — the page's rule, stated in draughtsman's own terms.

They are not gallery models, so `conftest.EXAMPLES` does not see them and the
parametrised checks in `test_render.py` do not run on them. This file is those
checks for these two, plus the three things the slot asked for.
"""

import json
import re

import pytest

from conftest import ROOT
from draughtsman.check import check
from draughtsman.facts import Graph
from draughtsman.render import CAPTION_MIN_W, DETAIL_SIZE, render
from draughtsman.spec import load

TUBE = ROOT / "examples" / "tube"

#: The slot each spec is drawn for, in CSS px, as bugarach measured it.
SLOTS = {"front-page": 1203, "front-page-phone": 395}


def _spec(name):
    return load(json.loads((TUBE / f"{name}.json").read_text()))


def _graph():
    return Graph(json.loads((TUBE / "graph.json").read_text()))


def _viewbox_width(svg: str) -> float:
    return float(re.search(r'viewBox="0 0 ([\d.]+) ', svg).group(1))


@pytest.mark.parametrize("name", SLOTS)
def test_the_committed_figure_is_current(name):
    assert render(_spec(name), _graph()) == (TUBE / f"{name}.svg").read_text(), (
        f"examples/tube/{name}.svg is stale — re-run `draughtsman render "
        f"examples/tube/{name}.json -o examples/tube/{name}.svg` and commit it.")


@pytest.mark.parametrize("name", SLOTS)
def test_it_covers_the_graph_and_clears_its_type_floor(name):
    """`check` runs the legibility gate because `output.width` is set, so an
    empty error list is the floor holding, not only coverage."""
    result = check(_spec(name), _graph())
    assert result.errors == []
    assert result.counts.exactly_once == result.counts.traced


@pytest.mark.parametrize("name", SLOTS)
def test_the_spec_states_its_slot_at_one_to_one(name):
    """The budget is the slot only if min_type is DETAIL_SIZE in px. Change either
    and the gate still passes while measuring something other than the page."""
    doc = json.loads((TUBE / f"{name}.json").read_text())
    assert doc["output"] == {"width": f"{SLOTS[name]}px",
                             "min_type": f"{DETAIL_SIZE:g}px"}


@pytest.mark.parametrize("name", SLOTS)
def test_it_fits_its_slot_without_being_scaled_down(name):
    svg = (TUBE / f"{name}.svg").read_text()
    assert _viewbox_width(svg) <= SLOTS[name]


@pytest.mark.parametrize("name", SLOTS)
def test_it_names_no_axis_it_would_have_to_name_twice(name):
    """Queue item 2: the glyph legend names every glyphed axis after the first
    glyphed stage, and tube's middle axis is cells for three stages and channels
    after the kernel bank. These figures draw no glyphs, so no legend row claims
    one name for both, and each stage says which it is in its own detail."""
    svg = (TUBE / f"{name}.svg").read_text()
    assert "ds-legend-glyph" not in svg
    assert "cells × frames" in svg
    assert "channels × frames, from here on" in svg


@pytest.mark.parametrize("name", SLOTS)
def test_the_bypass_and_the_bank_are_drawn(name):
    """The tube acceptance test, for these two: the fan-out to four kernels,
    the bypass, and the concat it rejoins at."""
    svg = (TUBE / f"{name}.svg").read_text()
    assert svg.count("σ") >= 4
    assert ">bypass<" in svg
    assert 'data-stage="concat"' in svg


@pytest.mark.parametrize("name", SLOTS)
def test_the_caption_credits_draughtsman(name):
    svg = (TUBE / f"{name}.svg").read_text()
    assert "Drawn by draughtsman from a torch.jit.trace" in re.sub(r"\s+", " ", svg)


def test_the_caption_floor_still_holds_where_no_width_is_stated():
    """The phone figure is 395 wide only because its stated width outranks the
    caption floor. Take the width away and the floor must come back, or every
    captioned figure without an `output` block just lost its protection."""
    doc = json.loads((TUBE / "front-page-phone.json").read_text())
    del doc["output"]
    svg = render(load(doc), _graph())
    assert _viewbox_width(svg) >= CAPTION_MIN_W


def test_a_label_beside_a_vertical_run_clears_its_own_line():
    """The phone figure is the first committed top-to-bottom figure with a
    labelled edge, and its `bypass` was drawn astride the line it names —
    `tests/test_edge_labels.py` checks labels against boxes and each other, and
    `tools/edge_collisions.py` checks paths against boxes, so neither could see a
    path crossing its own label. bugarach's label check did."""
    from draughtsman.render import _label_rect, _place_label
    from draughtsman.text import width
    x, y = _place_label([(100.0, 0.0), (100.0, 200.0)], "bypass", True, [])
    left, _, right, _ = _label_rect(x, y, width("bypass", DETAIL_SIZE))
    assert right <= 100.0 or left >= 100.0, (left, right)
