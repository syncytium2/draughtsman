"""SPEC.md §6 — generate, commit, verify.

The committed figure must be exactly what the committed spec and graph produce.
A model change that would move the figure then turns CI red instead of shipping a
picture of a model that no longer exists.

THIS TEST NEEDS NEITHER TORCH NOR GRAPHVIZ, which is the whole reason stage 3 is
ours rather than a system binary's. SPEC.md §8.2 worried that the staleness test
would drag graphviz into CI, in an estate where "a skip is what silence looks like
when it is being careful". There is nothing here to skip.
"""

import json
import re

import pytest

from conftest import EXAMPLES, IDS
from draughtsman.facts import Graph
from draughtsman.render import render
from draughtsman.spec import load


@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_committed_figure_is_current(d):
    """Every committed model, not just the first. A spec edited without
    regenerating its figure is a repo shipping a picture of something else."""
    spec = load(json.loads((d / "spec.json").read_text()))
    graph = Graph(json.loads((d / "graph.json").read_text()))
    assert render(spec, graph) == (d / "figure.svg").read_text(), (
        f"{d}/figure.svg is stale — re-run "
        f"`draughtsman render {d}/spec.json -o {d}/figure.svg` and commit it."
    )


@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_every_committed_model_covers_its_graph(d):
    """The gallery is a regression sheet; this is the half of it a machine can
    check. Nine models passing by eye on the day they were made is not a
    property that stays true."""
    from draughtsman.check import check
    spec = load(json.loads((d / "spec.json").read_text()))
    result = check(spec, Graph(json.loads((d / "graph.json").read_text())))
    assert result.errors == []
    assert result.counts.exactly_once == result.counts.traced


def test_render_is_byte_stable_across_runs(tube_spec, tube_graph):
    assert render(tube_spec, tube_graph) == render(tube_spec, tube_graph)


def test_figure_carries_no_stylesheet_and_no_script(example_dir):
    """SPEC.md §4: ship no styling, inherit from the embedding page."""
    svg = (example_dir / "figure.svg").read_text()
    assert "<style" not in svg
    assert "<script" not in svg
    assert "@import" not in svg


def test_fills_are_inline_style_not_presentation_attributes(example_dir):
    """A `fill="…"` loses to any host rule. `.arch rect { fill: … }` in the
    embedding page repainted every glyph one flat colour the first time this was
    tried, so every fill here has to outrank that."""
    svg = (example_dir / "figure.svg").read_text()
    assert ' fill="' not in svg
    assert "style=\"fill:" in svg


def test_the_figure_says_what_the_reader_needs(example_dir):
    """SPEC.md §9: the fan-out to four kernels, the bypass, and the concat.
    All five tools in §2 failed this."""
    svg = (example_dir / "figure.svg").read_text()
    assert svg.count("ds-lane") == 4          # four kernels, drawn as four lanes
    # The bypass is distinguished by its LABEL, and deliberately not by dashing.
    # bugarach's eab8e59 replaced a diagram that "drew the bypass as a dashed
    # afterthought": it is a first-class fifth channel into the concat, and dashed
    # reads as optional. Asserting it is solid is the point, not an omission.
    assert "ds-edge-dashed" not in svg
    assert ">bypass<" in svg
    assert "concatenate" in svg


def test_ink_on_the_page_inherits_and_ink_on_a_box_does_not(example_dir):
    """SPEC.md §4 says inherit from the embedding page. Half-implementing that —
    pinning dark ink onto a ground the page owns — makes the title, the caption
    and every edge invisible on a dark page, which is what a README rendered in
    GitHub's dark theme is.

    So the split is by what a thing sits on. On a box fill this file chose:
    pinned. On the page: `currentColor`, still inline so a host rule cannot
    repaint it, and still black when the file stands alone.
    """
    svg = (example_dir / "figure.svg").read_text()

    def style_of(pattern):
        m = re.search(pattern, svg)
        assert m, f"no element matched {pattern}"
        return m.group(0)

    assert "currentColor" in style_of(r'<text class="ds-title"[^>]*>')
    assert "currentColor" in style_of(r'<text class="ds-caption"[^>]*>')
    assert "currentColor" in style_of(r'<path class="ds-edge[^>]*>')
    assert "currentColor" in style_of(r'<marker[^>]*>.*?</marker>')

    # a stage's own label sits on a fill this file chose, so it stays pinned
    box_label = re.search(r'<g class="ds-stage[^>]*>.*?(<text[^>]*>)', svg)
    assert box_label and "currentColor" not in box_label.group(1)


def test_a_standalone_figure_still_has_ink(example_dir):
    """`currentColor` with no host resolves to black, so a file opened directly
    or rasterised for the PNG export looks exactly as it did before."""
    svg = (example_dir / "figure.svg").read_text()
    assert "<style" not in svg          # nothing is setting `color` for itself
    assert 'style="color' not in svg    # ... including on the root
