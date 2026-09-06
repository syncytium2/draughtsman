"""Stage 2 with nobody in the loop: `abstract --by-module`.

The tool's second stage was a prompt, and a prompt is addressed to whoever
answers it. Some people will not put an agent there. What they had was `ui` on
an empty spec -- a sorting job on Whisper's 271 nodes before any judgement could
start -- and no sentence anywhere saying even that existed.

`scaffold` groups by the registered module each node ran in, which is the one
grouping the trace already carries and that needs no judgement. The properties
below are what make it a safe starting point rather than a wrong answer: every
traced node placed, arrows from the trace, no number typed, no name invented,
`check` green. Whether the grouping is any GOOD is exactly what it does not
claim, and the caption on the figure says so.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from draughtsman import cli
from draughtsman.abstract import MIN_STAGES, _max_depth, scaffold, scaffold_depth
from draughtsman.check import check
from draughtsman.facts import Graph, bare_numbers
from draughtsman.render import render
from draughtsman.spec import load

ROOT = Path(__file__).resolve().parents[1]
GRAPHS = sorted(ROOT.glob("examples/gallery/*/graph.json")) + [
    ROOT / "examples" / "tube" / "graph.json"]


def _graph(path: Path) -> Graph:
    return Graph(json.loads(path.read_text()))


@pytest.mark.parametrize("path", GRAPHS, ids=[p.parent.name for p in GRAPHS])
def test_every_scaffold_passes_check_with_no_edge_complaint(path):
    """Green by construction, and not by luck: the arrows are the trace's own
    derivation, so `check` can neither find one unbacked nor one missing."""
    graph = _graph(path)
    doc, _ = scaffold(graph)
    result = check(load(doc), graph)
    assert result.ok, result.errors
    edge_talk = [w for w in result.warnings if "->" in w]
    assert not edge_talk, edge_talk


@pytest.mark.parametrize("path", GRAPHS, ids=[p.parent.name for p in GRAPHS])
def test_every_traced_node_is_in_exactly_one_stage_and_nothing_is_elided(path):
    graph = _graph(path)
    doc, _ = scaffold(graph)
    placed = [n for s in doc["stages"] for n in s["nodes"]]
    assert sorted(placed) == sorted(graph.traced + [r["id"] for r in graph.inputs])
    assert len(placed) == len(set(placed))
    assert not doc.get("elided")


@pytest.mark.parametrize("path", GRAPHS, ids=[p.parent.name for p in GRAPHS])
def test_the_scaffold_types_no_number_in_a_detail_line(path):
    """Names are module paths and may carry an index -- `blocks.0` is a name.
    Detail lines are where a fact would be typed, and none is."""
    doc, _ = scaffold(_graph(path))
    typed = [(s["id"], d) for s in doc["stages"] for d in s["detail"]
             if bare_numbers(d)]
    assert not typed, typed


@pytest.mark.parametrize("path", GRAPHS, ids=[p.parent.name for p in GRAPHS])
def test_every_scaffold_renders(path):
    graph = _graph(path)
    doc, _ = scaffold(graph)
    assert render(load(doc), graph).startswith("<svg")


@pytest.mark.parametrize("path", GRAPHS, ids=[p.parent.name for p in GRAPHS])
def test_the_depth_is_the_shallowest_that_reaches_the_floor(path):
    """One sentence, checked: the shallowest depth with MIN_STAGES runs, else the
    deepest there is. A shallower depth than the chosen one must fall short."""
    graph = _graph(path)
    doc, depth = scaffold(graph)
    runs = len(doc["stages"]) - len(graph.inputs)
    if runs < MIN_STAGES:
        assert depth == _max_depth(graph), (depth, runs)
    for shallower in range(1, depth):
        shallow, _ = scaffold(graph, depth=shallower)
        assert len(shallow["stages"]) - len(graph.inputs) < MIN_STAGES, shallower


def test_a_forced_depth_is_honoured_and_zero_is_refused():
    graph = _graph(ROOT / "examples/gallery/resnet/graph.json")
    shallow, depth = scaffold(graph, depth=1)
    assert depth == 1
    assert [s["name"] for s in shallow["stages"]][1:] == ["stem", "bn", "blocks", "head"]
    with pytest.raises(ValueError):
        scaffold(graph, depth=0)


def test_the_stage_graph_cannot_cycle_because_runs_are_contiguous():
    """U-Net has three skips across its whole depth. Contiguous runs in trace
    order put every producer before its consumer, so every arrow points
    forward; `check` would name a cycle as an error and finds none."""
    graph = _graph(ROOT / "examples/gallery/unet/graph.json")
    doc, _ = scaffold(graph)
    order = {s["id"]: i for i, s in enumerate(doc["stages"])}
    assert all(order[e["from"]] < order[e["to"]] for e in doc["edges"])


def test_a_stage_that_exits_at_two_shapes_names_both_and_chooses_neither():
    """`{stage.out_shape}` is an error on such a stage by design; the scaffold
    must not resolve the doubt by picking, so it writes one line per exit."""
    graph = _graph(ROOT / "examples/gallery/unet/graph.json")
    doc, _ = scaffold(graph)
    enc1 = next(s for s in doc["stages"] if s["name"] == "enc1")
    shapes = [d for d in enc1["detail"] if d.startswith("{node:")]
    assert len(shapes) == 2, enc1["detail"]


def test_the_same_graph_scaffolds_to_the_same_bytes():
    graph = _graph(ROOT / "examples/gallery/whisper/graph.json")
    assert scaffold(graph) == scaffold(graph)


def test_the_caption_says_nothing_was_judged():
    doc, depth = scaffold(_graph(ROOT / "examples/gallery/lenet/graph.json"))
    assert "judged" in doc["caption"] and f"depth {depth}" in doc["caption"]


def test_the_cli_writes_the_spec_and_then_refuses_to_overwrite_it(tmp_path, capsys):
    """SPEC.md §8.3: a re-run must never eat an edit. The same guard the prompt
    path has, on the path that actually writes."""
    graph = ROOT / "examples/gallery/lenet/graph.json"
    out = tmp_path / "spec.json"
    assert cli.main(["abstract", str(graph), "-o", str(out), "--by-module"]) == 0
    doc = json.loads(out.read_text())
    assert doc["stages"] and doc["edges"]
    assert "draughtsman ui" in capsys.readouterr().err
    out.write_text('{"edited": true}')
    with pytest.raises(SystemExit):
        cli.main(["abstract", str(graph), "-o", str(out), "--by-module"])
    assert json.loads(out.read_text()) == {"edited": True}
    assert cli.main(["abstract", str(graph), "-o", str(out), "--by-module",
                     "--force"]) == 0
    assert json.loads(out.read_text())["stages"]


def test_the_cli_prints_the_spec_when_no_output_is_named(capsys):
    graph = ROOT / "examples/gallery/lenet/graph.json"
    assert cli.main(["abstract", str(graph), "--by-module"]) == 0
    assert json.loads(capsys.readouterr().out)["stages"]


def test_depth_without_by_module_is_refused():
    graph = ROOT / "examples/gallery/lenet/graph.json"
    with pytest.raises(SystemExit):
        cli.main(["abstract", str(graph), "--depth", "2"])


def test_the_prompt_path_is_unchanged(capsys):
    """Adding a second way through stage 2 must not move the first."""
    graph = ROOT / "examples/gallery/lenet/graph.json"
    assert cli.main(["abstract", str(graph)]) == 0
    assert capsys.readouterr().out.startswith("You are doing stage 2")


def test_scaffold_depth_agrees_with_scaffold():
    graph = _graph(ROOT / "examples/gallery/resnet/graph.json")
    assert scaffold(graph)[1] == scaffold_depth(graph) == 2
