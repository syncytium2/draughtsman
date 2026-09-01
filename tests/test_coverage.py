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
    # An INTERIOR node of the kernel bank. This used to pop the last node of
    # `widen`, which is the one `mean` consumes -- so eliding it severed the
    # widen -> mean arrow, and once the edge assertion existed this test failed
    # for a reason that had nothing to do with elision. Naming the node keeps the
    # test about the thing it is named after.
    def drop(d):
        dog = next(s for s in d["stages"] if s["id"] == "dog")
        dog["nodes"].remove("n0050")
        d["elided"] = [{"nodes": ["n0050"], "reason": "shape bookkeeping"}]
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


# ---------------------------------------------------------------------------------
# A TRACED CONSTANT MAY BE AN INITIALISATION, AND THE TRACE CANNOT SAY WHICH.
#
# bugarach's `tube` drew "max-pool, width 3" from `{node:n0031.constants.kernel_size}`.
# The width is `2 * kmin + 1` with `kmin` read off a TRAINED parameter: 3 at
# initialisation, 9-15 once trained. `int()` on a tensor leaves tensor-land, so the
# width arrives as a bare literal and no walk of graph.json recovers where it came
# from. torch says it baked something; these tests pin that draughtsman listens.
# ---------------------------------------------------------------------------------

HAZARD = [{"kind": "python_value_baked", "file": "tube.py", "line": 139,
           "message": "Converting a tensor to a Python integer ..."}]


def _graph_with(doc, hazards):
    from draughtsman.facts import Graph
    doc = copy.deepcopy(doc)
    if hazards is None:
        doc.pop("hazards", None)
    else:
        doc["hazards"] = hazards
    return Graph(doc)


def _spec_quoting_a_constant(doc, *, declared=None):
    doc = copy.deepcopy(doc)
    for stage in doc["stages"]:
        if stage["id"] == "head":
            stage["detail"] = ["dilation {node:n0149.constants.dilation}"]
    doc.pop("constants", None)
    if declared:
        doc["constants"] = declared
    return load(doc)


def test_quoting_a_traced_constant_under_a_bake_hazard_is_an_error(
        tube_spec_doc, tube_graph_doc):
    """The figure may not state a traced constant as a fact while the tracer is
    reporting that it baked Python values — not without saying which kind it is."""
    result = check(_spec_quoting_a_constant(tube_spec_doc),
                   _graph_with(tube_graph_doc, HAZARD))
    assert any("n0149.constants.dilation" in e for e in result.errors)
    assert not result.ok


def test_declaring_the_constant_architectural_clears_it(
        tube_spec_doc, tube_graph_doc):
    """A line in the spec, which is a decision in a diff — the same shape as an
    explicit elision, and for the same reason."""
    result = check(
        _spec_quoting_a_constant(
            tube_spec_doc,
            declared={"n0149.constants.dilation": "d = 2 ** i, set by depth"}),
        _graph_with(tube_graph_doc, HAZARD))
    assert result.ok
    assert not any("n0149" in e for e in result.errors)


def test_an_empty_reason_does_not_clear_it(tube_spec_doc, tube_graph_doc):
    """Otherwise the declaration is a checkbox rather than a justification."""
    result = check(
        _spec_quoting_a_constant(tube_spec_doc,
                                 declared={"n0149.constants.dilation": "   "}),
        _graph_with(tube_graph_doc, HAZARD))
    assert not result.ok


def test_no_hazard_means_constants_are_quotable_freely(
        tube_spec_doc, tube_graph_doc):
    """The rule is not 'constants are suspect'. Most models bake nothing, and on
    those a traced constant IS an architectural fact."""
    result = check(_spec_quoting_a_constant(tube_spec_doc),
                   _graph_with(tube_graph_doc, []))
    assert result.ok


def test_a_graph_predating_hazard_recording_says_so(tube_spec_doc, tube_graph_doc):
    """Silence from an old trace is not a clean bill of health, and the two must
    not read the same."""
    result = check(_spec_quoting_a_constant(tube_spec_doc),
                   _graph_with(tube_graph_doc, None))
    assert any("predates hazard recording" in w for w in result.warnings)


def test_a_declaration_for_a_constant_nobody_quotes_is_flagged(
        tube_spec_doc, tube_graph_doc):
    """A justification outliving the text it justified is how the list this
    mechanism exists to avoid grows back."""
    doc = copy.deepcopy(tube_spec_doc)
    doc["constants"] = {"n0031.constants.kernel_size": "stale justification"}
    result = check(load(doc), _graph_with(tube_graph_doc, HAZARD))
    assert any("kernel_size" in w and "no text quotes it" in w
               for w in result.warnings)


def test_the_committed_tube_graph_records_the_hazard(tube_graph):
    """tube.py:139 is `kmin = int(exp(log_center).min().clamp(1, k))`. If this
    ever reads empty, the figure lost the one signal that its max-pool width is
    an initialisation."""
    assert tube_graph.hazards_recorded
    assert any(h["file"] == "tube.py" and h["kind"] == "python_value_baked"
               for h in tube_graph.hazards)


def test_the_committed_figure_does_not_state_the_pool_width(example_dir):
    """The width is fitted, so no number for it belongs in a figure that
    describes the architecture."""
    svg = (example_dir / "figure.svg").read_text()
    assert "width 3" not in svg
    assert "width fitted" in svg


def test_a_hazard_inside_torch_does_not_demand_a_declaration(
        tube_spec_doc, tube_graph_doc):
    """`nn.LSTM` bakes a bool in torch's own `rnn.py` on every trace. That is how
    a stock module was CONSTRUCTED, not a fitted quantity in the model being
    drawn, and treating the two alike would make the rule noise — which is how a
    check stops being read."""
    internal = [{"kind": "python_value_baked", "file": "rnn.py", "line": 328,
                 "internal": True, "message": "..."}]
    result = check(_spec_quoting_a_constant(tube_spec_doc),
                   _graph_with(tube_graph_doc, internal))
    assert result.ok
    assert any("inside torch itself" in n for n in result.notes)


def test_a_torch_only_hazard_still_reads_differently_from_none(
        tube_spec_doc, tube_graph_doc):
    """"No hazard" and "a hazard that is not about your model" are different
    facts, and the report says which."""
    internal = [{"kind": "python_value_baked", "file": "rnn.py", "line": 328,
                 "internal": True, "message": "..."}]
    with_haz = check(_spec_quoting_a_constant(tube_spec_doc),
                     _graph_with(tube_graph_doc, internal))
    without = check(_spec_quoting_a_constant(tube_spec_doc),
                    _graph_with(tube_graph_doc, []))
    assert any("inside torch" in n for n in with_haz.notes)
    assert not any("inside torch" in n for n in without.notes)


def test_the_committed_lstm_hazard_is_torch_s_and_not_the_model_s():
    """A live example of the split, so it is not only tested on a synthetic one."""
    import json as _json
    from pathlib import Path as _Path
    from draughtsman.facts import Graph
    root = _Path(__file__).resolve().parent.parent
    g = Graph(_json.loads((root / "examples" / "gallery" / "lstm"
                           / "graph.json").read_text()))
    assert g.hazards, "nn.LSTM bakes a bool; the trace should record it"
    assert all(h["file"] == "rnn.py" for h in g.hazards)
    assert g.model_hazards == []
# -- the arrows, against the trace ---------------------------------------------
# SPEC.md §5 asserts placement and stops. Every node can sit in exactly one stage
# while the arrows between those stages say something the model does not do, and
# the arrows are most of what a reader takes from a figure.


def test_an_arrow_the_trace_does_not_have_is_an_error(spec_doc, tube_graph):
    """`raster -> dog` skips the pool and the mean. Nothing in `dog` consumes
    anything in `raster`, and the figure would be asserting a path the model
    does not have."""
    def add(d):
        d["edges"].append({"from": "raster", "to": "dog"})
    result = check(_mutate(spec_doc, add), tube_graph)
    assert not result.ok
    assert any("raster -> dog is drawn but no node" in e for e in result.errors)


def test_an_untraced_arrow_may_be_declared_with_a_reason(spec_doc, tube_graph):
    """The VAE's noise is the real case: a reader wants the sample to depend on
    the mean and the deviation, and the trace records only a shape being read.
    That is a decision, so it is declarable -- and it lands in the report rather
    than passing silently."""
    def add(d):
        d["edges"].append({"from": "raster", "to": "dog",
                           "untraced": "the model does this; the trace does not"})
    result = check(_mutate(spec_doc, add), tube_graph)
    assert result.ok
    assert any("drawn but not traced" in n for n in result.notes)


def test_a_declaration_without_a_reason_does_not_silence_it(spec_doc, tube_graph):
    """An empty reason is not a decision, and must not buy the same pass that a
    stated one does."""
    def add(d):
        d["edges"].append({"from": "raster", "to": "dog", "untraced": ""})
    assert not check(_mutate(spec_doc, add), tube_graph).ok


def test_a_traced_path_the_figure_omits_warns_but_does_not_fail(spec_doc,
                                                                tube_graph):
    """The other direction CANNOT be an error. `raster -> mean` is real -- the
    mean divides by the raster's channel count -- and it is a shape dependency no
    reader wants drawn. Collapsing a repeated block buries fan-out the same way.
    So it is reported and it does not fail, because a check that cried wolf here
    would be turned off."""
    result = check(_mutate(spec_doc, lambda d: None), tube_graph)
    assert result.ok
    assert any("raster -> mean is in the trace and not in the figure" in w
               for w in result.warnings)
