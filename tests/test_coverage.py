"""SPEC.md §5 — the check that can fail, and the five omissions it exists to catch."""

import copy
import json

import pytest

from draughtsman.check import check
from draughtsman.spec import load


def test_committed_spec_covers_every_node(tube_spec, tube_graph):
    result = check(tube_spec, tube_graph)
    assert result.errors == []
    covered = {n for s in tube_spec.stages for n in s.nodes}
    assert set(tube_graph.traced) <= covered


def test_the_pytorch_graph_omissions_are_all_drawn(tube_spec, tube_graph):
    """pytorch-graph rendered head.0 … head.12 and dropped everything else.

    It omitted the max-pool, the mean over cells, the four DoG kernels, the
    bypass and the concat — which is to say, the architecture — and reported
    success. Each of those five is a specific node in graph.json, so each of them
    is a specific assertion here. This is the regression suite of SPEC.md §2 made
    executable rather than kept as a folder of PNGs.
    """
    stage_of = {n: s.id for s in tube_spec.stages for n in s.nodes}
    kinds = {nid: tube_graph.nodes[nid]["kind"] for nid in tube_graph.traced}

    def sole(kind):
        found = [n for n, k in kinds.items() if k == kind]
        assert len(found) == 1, f"expected one {kind}, found {found}"
        return found[0]

    for kind in ("aten::max_pool1d", "aten::cat"):
        assert sole(kind) in stage_of, f"{kind} is in no stage"

    # the mean over cells
    means = [n for n in tube_graph.traced
             if kinds[n] == "aten::div" and tube_graph.nodes[n]["out_shape"]
             == [1, 1, 600]]
    assert means and all(n in stage_of for n in means)

    # the kernel bank: one convolution whose weight is computed, four channels out
    dog = [n for n in tube_graph.traced
           if kinds[n] == "aten::_convolution"
           and tube_graph.nodes[n]["weight_shape"] is None]
    assert len(dog) == 1
    assert dog[0] in stage_of
    assert tube_graph.nodes[dog[0]]["out_shape"][1] == 4

    # the bypass: the concat is fed by the mean AND by the bank, not by the bank
    # alone. A figure drawn from a graph missing this edge is a linear stack.
    cat = tube_graph.nodes[sole("aten::cat")]
    assert set(cat["tensor_inputs"]) == {means[-1], dog[0]}


def _mutate(spec_doc, fn):
    doc = copy.deepcopy(spec_doc)
    fn(doc)
    return load(doc)


@pytest.fixture(scope="session")
def spec_doc(example_dir):
    return json.loads((example_dir / "spec.json").read_text())


def test_dropped_node_is_an_error(spec_doc, tube_graph):
    spec = _mutate(spec_doc, lambda d: d["stages"][1]["nodes"].pop())
    result = check(spec, tube_graph)
    assert not result.ok
    assert any("is in no stage" in e for e in result.errors)


def test_node_in_two_stages_is_an_error(spec_doc, tube_graph):
    spec = _mutate(spec_doc,
                   lambda d: d["stages"][2]["nodes"].append(d["stages"][1]["nodes"][0]))
    result = check(spec, tube_graph)
    assert not result.ok
    assert any("appears in 2 places" in e for e in result.errors)


def test_elision_needs_a_reason(spec_doc, tube_graph):
    def drop(d):
        nid = d["stages"][1]["nodes"].pop()
        d["elided"] = [{"nodes": [nid], "reason": "  "}]
    result = check(_mutate(spec_doc, drop), tube_graph)
    assert any("no reason" in e for e in result.errors)


def test_elision_with_a_reason_passes(spec_doc, tube_graph):
    def drop(d):
        nid = d["stages"][1]["nodes"].pop()
        d["elided"] = [{"nodes": [nid], "reason": "shape bookkeeping"}]
    assert check(_mutate(spec_doc, drop), tube_graph).ok


def test_unknown_node_id_is_an_error(spec_doc, tube_graph):
    spec = _mutate(spec_doc, lambda d: d["stages"][0]["nodes"].append("n9999"))
    assert any("graph.json does not have" in e
               for e in check(spec, tube_graph).errors)


def test_lane_labels_must_match_the_model(spec_doc, tube_graph):
    """The agent names the lanes; the model says how many. If they disagree the
    labels are wrong, and a wrong label is worse than none."""
    def relabel(d):
        for s in d["stages"]:
            if s.get("lanes"):
                s["lanes"]["labels"].append("σ₅")
    result = check(_mutate(spec_doc, relabel), tube_graph)
    assert any("labels 5 lanes" in e for e in result.errors)


def test_cycle_in_the_stage_graph_is_an_error(spec_doc, tube_graph):
    spec = _mutate(spec_doc,
                   lambda d: d["edges"].append({"from": "score", "to": "raster"}))
    assert any("cycle" in e for e in check(spec, tube_graph).errors)


def test_edge_to_nowhere_is_an_error(spec_doc, tube_graph):
    spec = _mutate(spec_doc,
                   lambda d: d["edges"].append({"from": "score", "to": "ghost"}))
    assert any("names no stage" in e for e in check(spec, tube_graph).errors)


def test_a_typed_number_is_reported(spec_doc, tube_graph):
    """SPEC.md §4: the agent supplies no facts. It cannot be forbidden outright —
    '1×1 conv' is a name — so it is reported and never silent."""
    spec = _mutate(spec_doc,
                   lambda d: d["stages"][0]["detail"].append("1149 parameters"))
    result = check(spec, tube_graph)
    assert result.ok
    assert any("literal number" in w for w in result.warnings)


# --------------------------------------------------------------------------------
# There is one place that counts coverage. Everything that displays a coverage
# number reads these, because an indicator that derives its own arithmetic is an
# indicator that can disagree with the check it indicates — and this one is the
# entire safety argument for letting an agent into the pipeline.

def test_counts_on_the_committed_spec(tube_spec, tube_graph):
    c = check(tube_spec, tube_graph).counts
    assert (c.traced, c.exactly_once, c.duplicated, c.unplaced) == (47, 47, 0, 0)
    # The raster stage names the model's input, which is addressable but is not a
    # traced node. It is reported separately rather than inflating the coverage
    # numerator past its own denominator.
    assert c.untraced_claimed == 1


def test_a_node_in_two_stages_shows_in_the_number_not_just_the_colour(
        spec_doc, tube_graph):
    """The failure a green-looking ratio would hide."""
    from draughtsman.check import summary

    def dup(d):
        d["stages"][2]["nodes"].append(d["stages"][1]["nodes"][0])
    result = check(_mutate(spec_doc, dup), tube_graph)
    assert not result.ok
    assert result.counts.duplicated == 1
    assert result.counts.exactly_once == 46
    assert "1 in two" in summary(result.counts)


def test_an_unplaced_node_shows_in_the_number(spec_doc, tube_graph):
    from draughtsman.check import summary
    result = check(_mutate(spec_doc, lambda d: d["stages"][1]["nodes"].pop()),
                   tube_graph)
    assert result.counts.unplaced == 1
    assert result.counts.exactly_once == 46
    assert "1 unplaced" in summary(result.counts)


def test_the_report_and_the_counts_cannot_disagree(tube_spec, tube_graph):
    from draughtsman.check import report
    result = check(tube_spec, tube_graph)
    text = report(result)
    assert f"{result.counts.exactly_once}/{result.counts.traced}" in text
    assert str(result.counts.traced) in text
