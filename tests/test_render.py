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
    assert "ds-edge-dashed" in svg            # the bypass, distinguished
    assert ">bypass<" in svg
    assert "concatenate" in svg
