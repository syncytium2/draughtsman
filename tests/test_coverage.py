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
    """Mutate tube's spec for a COVERAGE assertion, with the print gate removed.

    THESE TESTS ARE ABOUT WHAT COVERAGE MEANS, and `output` makes `check` answer a
    second, unrelated question: would this figure be legible at the size it
    declares. Once tube declared `6in`/`6pt`, every mutation here was judged on
    both, and a mutation that adds an edge is exactly the kind that widens a
    figure — `test_an_untraced_arrow_may_be_declared_with_a_reason` adds one that
    forks the graph and takes tube from 589 units to 934, at every wrap value
    from 455 down to 105.

    That test then failed, under a name that says nothing about legibility. A test
    that fails for a reason its name does not describe has stopped saying what it
    means, and the next person to read the failure looks in the wrong file.

    So the gate comes off here and stays on where it belongs: the committed specs,
    and `tests/test_layout_shape.py`, which is where a declared output size is
    actually asserted.
    """
    doc = copy.deepcopy(spec_doc)
    doc.pop("output", None)
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
    # An interior node of the DILATED STACK, whose members all carry the same
    # shape. Eliding anything interior necessarily gives its stage a second exit
    # -- whatever fed the elided node now feeds something outside -- so the node
    # has to be one where the two exits AGREE, or `{stage.out_shape}` is genuinely
    # ambiguous and refuses. See test_elision_can_make_a_stage_ambiguous below.
    #
    # This is the third node this test has had to name. It popped `widen`'s last
    # node until the edge assertion landed, then an interior node of the kernel
    # bank until the exit check landed. Each move was the test being told
    # something true about the elision it was performing.
    def drop(d):
        head = next(s for s in d["stages"] if s["id"] == "head")
        head["nodes"].remove("n0150")
        d["elided"] = [{"nodes": ["n0150"], "reason": "activation, not structure"}]
    result = check(_mutate(spec_doc, drop), tube_graph)
    assert result.errors == []


def test_elision_can_make_a_stage_ambiguous(spec_doc, tube_graph):
    """The other half, and the reason the test above had to move.

    Eliding an interior node of the kernel bank orphans the `arange` that built
    the kernel window, so the stage exits through both it and the convolution —
    257 against 1x4x600. `{stage.out_shape}` then has no single answer, and the
    old code silently returned the last one.
    """
    def drop(d):
        dog = next(s for s in d["stages"] if s["id"] == "dog")
        dog["nodes"].remove("n0050")
        d["elided"] = [{"nodes": ["n0050"], "reason": "shape bookkeeping"}]
    result = check(_mutate(spec_doc, drop), tube_graph)
    assert any("do not agree" in e for e in result.errors), result.errors
    # and it names both candidates, so the author can pick one
    assert any("n0046" in e and "n0116" in e for e in result.errors)


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


def test_an_elided_node_does_not_sever_the_path_through_it(spec_doc, tube_graph):
    """ELIDING SAYS A READER DOES NOT NEED TO SEE AN OPERATION. It does not say
    the data stopped flowing through it.

    A model that elides both of its permutes -- they sit between stages -- had two
    correct arrows reported as unbacked when those elisions were treated as gaps — a
    check calling a right figure wrong, which is how a check gets switched off.
    """
    def elide_the_join(d):
        # `mean` is what `dog` and the bypass both consume; elide its last node
        # and the arrows either side of it must still hold.
        mean = next(s for s in d["stages"] if s["id"] == "mean")
        nid = mean["nodes"].pop()
        d["elided"] = [{"nodes": [nid], "reason": "axis bookkeeping"}]
    result = check(_mutate(spec_doc, elide_the_join), tube_graph)
    assert result.ok, [e for e in result.errors]
    assert not any("is drawn but no node" in e for e in result.errors)


# -- meters: a number drawn instead of read ------------------------------------


def _with_meters(doc, meters_by_stage):
    doc = copy.deepcopy(doc)
    for stage in doc["stages"]:
        if stage["id"] in meters_by_stage:
            stage["meters"] = meters_by_stage[stage["id"]]
    return load(doc)


def test_a_meter_must_resolve_to_a_number(spec_doc, tube_graph):
    """A bar drawn from '1x4x600' would be drawing the length of the string."""
    spec = _with_meters(spec_doc, {
        "dog": [{"value": "{stage.out_shape}", "label": "size"}],
        "head": [{"value": "{stage.out_shape}", "label": "size"}]})
    result = check(spec, tube_graph)
    assert not result.ok
    assert any("not a number" in e for e in result.errors)


def test_a_meter_on_one_stage_only_is_flagged(spec_doc, tube_graph):
    """Meters share a scale across the figure, so a series of one is a bar that
    is full by definition and compares with nothing."""
    spec = _with_meters(spec_doc, {"head": [{"value": "{stage.params}",
                                             "label": "params"}]})
    result = check(spec, tube_graph)
    assert result.ok          # decoration, not a lie
    assert any("compares with nothing" in w for w in result.warnings)


def test_meters_across_stages_pass(spec_doc, tube_graph):
    spec = _with_meters(spec_doc, {
        "dog": [{"value": "{stage.params}", "label": "params"}],
        "head": [{"value": "{stage.params}", "label": "params"}]})
    result = check(spec, tube_graph)
    assert result.ok
    assert not any("compares with nothing" in w for w in result.warnings)


def test_glyphs_must_agree_on_labels_and_scale(spec_doc, tube_graph):
    """One figure, one ruler. Two stages labelling their axes differently draw
    incomparable rectangles that a reader has every reason to compare."""
    def clash(d):
        for stage in d["stages"]:
            if stage["id"] == "dog":
                stage["glyph"] = {"of": "{stage.out_shape}", "axes": [1, 2],
                                  "labels": ["channels", "frames"]}
            if stage["id"] == "head":
                stage["glyph"] = {"of": "{stage.out_shape}", "axes": [1, 2],
                                  "labels": ["filters", "samples"]}
    result = check(_mutate(spec_doc, clash), tube_graph)
    assert not result.ok
    assert any("label their axes the same way" in e for e in result.errors)


# -- repeat: the count is the graph's, not the agent's --------------------------


def _repeating(doc, stage_id, template):
    doc = copy.deepcopy(doc)
    for stage in doc["stages"]:
        if stage["id"] == stage_id:
            stage["repeat"] = {"template": list(template)}
    return load(doc)


def test_a_repetition_the_graph_does_not_contain_is_an_error(spec_doc,
                                                             tube_graph):
    """`dog` is 26 kernel-construction ops and `head` is 12 conv/relu pairs. One
    is not copies of the other, and a figure drawing it as a stack would say the
    model does something it does not."""
    result = check(_repeating(spec_doc, "head", ["dog"]), tube_graph)
    assert not result.ok
    assert any("not a whole number of copies" in e for e in result.errors)


def test_a_template_naming_no_stage_is_an_error(spec_doc, tube_graph):
    result = check(_repeating(spec_doc, "head", ["nosuch"]), tube_graph)
    assert not result.ok
    assert any("names no stage" in e for e in result.errors)


def test_a_stage_cannot_repeat_itself(spec_doc, tube_graph):
    result = check(_repeating(spec_doc, "head", ["head"]), tube_graph)
    assert not result.ok
    assert any("includes itself" in e for e in result.errors)


# ---------------------------------------------------------------------------------
# EVERY NUMBER A FIGURE DRAWS NEEDS A NAME.
#
# Tony, reading the shipped tube figure: "each number needs to be defined. box from
# draughtsman says 1x30x600, then cells x frames. doesn't match." Three numbers, two
# names, at the very first box. The batch axis is 1 throughout an architecture figure
# and carries nothing, so the fix is to stop drawing it -- but only the spec's author
# knows WHICH axis that is, and only while it really is 1.
# ---------------------------------------------------------------------------------

def test_the_batch_axis_is_hidden_when_declared(tube_spec, tube_graph):
    from draughtsman.render import render
    svg = render(tube_spec, tube_graph)
    assert ">30×600<" in svg          # cells × frames: two numbers, two names
    assert ">1×30×600<" not in svg


def test_without_the_declaration_every_axis_is_drawn(tube_spec_doc, tube_graph):
    """The renderer never guesses. A traced [1, 1, 28, 28] has two axes of size
    one and only the spec's author knows which is the batch."""
    import copy
    from draughtsman.render import render
    doc = copy.deepcopy(tube_spec_doc)
    doc.pop("batch_axis", None)
    assert ">1×30×600<" in render(load(doc), tube_graph)


def test_hiding_an_axis_that_is_not_one_is_refused(tube_spec_doc, tube_graph):
    """`tube` reshapes to [30, 1, 600] midway -- cells folded INTO the batch --
    so a blanket 'drop axis 0' would delete the cell count and say nothing. The
    declaration is checked against what the figure actually draws."""
    import copy
    doc = copy.deepcopy(tube_spec_doc)
    doc["batch_axis"] = 1            # the CELL axis on the first two stages
    result = check(load(doc), tube_graph)
    assert not result.ok
    assert any("not 1" in e and "delete a number" in e for e in result.errors)


def test_an_indexed_axis_is_never_rebased(tube_spec, tube_graph):
    """`{stage.out_shape[1]}` names an axis by position. Hiding the batch axis
    must not silently shift what index 1 means, or the concat's '5 channels'
    would start reading the frame count."""
    from draughtsman.render import render
    svg = render(tube_spec, tube_graph)
    assert ">5 channels<" in svg


def test_the_figure_carries_no_british_spelling(example_dir):
    """Tony, on the front page: "get rid of british english throughout." The
    figure was the only one left, in the kernel bank's own label."""
    svg = (example_dir / "figure.svg").read_text()
    for word in ("normalised", "colour", "behaviour", "centre-surround"):
        assert word not in svg, f"{word!r} is in the shipped figure"


def test_the_glyph_and_the_labels_share_one_axis_numbering(tube_spec_doc,
                                                           tube_graph):
    """DECISIONS.md correction 5: one quantity, one implementation, and something
    that fails when it cannot be answered.

    `glyph.axes` indexes positionally into a resolved shape. If the text hid the
    batch axis and the glyph did not, a spec would carry two numberings — axis 1
    is "cells" to the glyph and "frames" to the label — and the picture would
    disagree with the words beside it while every check stayed green. Both go
    through the same `resolve`, so asking for an axis the reader cannot see is an
    error rather than a different tensor.
    """
    import copy
    from draughtsman.facts import FactError
    from draughtsman.render import render
    doc = copy.deepcopy(tube_spec_doc)
    assert doc.get("batch_axis") == 0
    for stage in doc["stages"]:
        if stage["id"] == "dog":
            stage["glyph"] = {"of": "{stage.out_shape}", "axes": [1, 2],
                              "labels": ["channels", "frames"]}
    with pytest.raises(FactError, match="axis 2"):
        render(load(doc), tube_graph)


def test_the_title_is_checked_for_the_hidden_axis_too(tube_spec_doc, tube_graph):
    """The title resolves {model.input_shape} through the same hiding, so it
    needs the same check — a claim nothing verifies is decoration."""
    import copy
    doc = copy.deepcopy(tube_spec_doc)
    doc["batch_axis"] = 1               # the cell axis, 30, in the model input
    doc["subtitle"] = "{model.input_shape} in"
    result = check(load(doc), tube_graph)
    assert any("the title" in e and "not 1" in e for e in result.errors)


def test_an_index_cannot_smuggle_the_hidden_axis_back(tube_spec_doc, tube_graph):
    """`{stage.out_shape}` hid the batch and `{stage.out_shape[0]}` handed it
    straight back, because 1 is a true number and nothing objected.

    Found by draughtsman-f0 reading the first version of this feature. It is
    DECISIONS.md correction 5's other half — not two implementations disagreeing,
    but one claim with a path it did not reach. A spec that declares an axis
    carries nothing has to mean it on every path.
    """
    import copy
    from draughtsman.facts import FactError
    from draughtsman.render import render
    doc = copy.deepcopy(tube_spec_doc)
    for stage in doc["stages"]:
        if stage["id"] == "raster":
            stage["detail"] = ["{stage.out_shape[0]}"]
    with pytest.raises(FactError, match="carries nothing"):
        render(load(doc), tube_graph)


def test_a_negative_index_names_the_same_axis(tube_spec_doc, tube_graph):
    """`[-3]` on a three-axis shape IS `[0]`. Comparing the literals would let
    it walk past the rule."""
    import copy
    from draughtsman.facts import FactError
    from draughtsman.render import render
    doc = copy.deepcopy(tube_spec_doc)
    for stage in doc["stages"]:
        if stage["id"] == "raster":
            stage["detail"] = ["{stage.out_shape[-3]}"]
    with pytest.raises(FactError, match="carries nothing"):
        render(load(doc), tube_graph)


def test_every_other_index_still_addresses_the_traced_shape(tube_spec, tube_graph):
    """Renumbering the survivors would silently move what index 1 means, which
    is the trap this convention exists to avoid. The concat says '5 channels'
    from `{stage.out_shape[1]}` against a traced [1, 5, 600]."""
    from draughtsman.render import render
    assert ">5 channels<" in render(tube_spec, tube_graph)


def test_a_positively_indexed_glyph_is_warned_about_under_a_batch_axis(
        tube_spec_doc, tube_graph):
    """U-Net's `axes: [1, 2]` with labels ["channels", "height"] means
    (channels, height) on a four-axis shape and (height, width) once the batch is
    hidden — both in range, so nothing errors and every rectangle becomes a
    square. Found by draughtsman-f0 before it shipped."""
    import copy
    doc = copy.deepcopy(tube_spec_doc)
    for stage in doc["stages"]:
        stage.pop("glyph", None)      # tube carries its own; this test owns none
        if stage["id"] == "raster":
            stage["glyph"] = {"of": "{stage.out_shape}", "axes": [0, 1],
                              "labels": ["cells", "frames"]}
    result = check(load(doc), tube_graph)
    assert result.ok, "positive indices into the drawn shape are legitimate"
    assert any("do not move when a leading axis is hidden" in w
               for w in result.warnings)


def test_a_negatively_indexed_glyph_is_not_warned_about(tube_spec_doc, tube_graph):
    """Negative indices are invariant under batch hiding, which is the whole
    reason to prefer them."""
    import copy
    doc = copy.deepcopy(tube_spec_doc)
    for stage in doc["stages"]:
        stage.pop("glyph", None)
        if stage["id"] == "raster":
            stage["glyph"] = {"of": "{stage.out_shape}", "axes": [-2, -1],
                              "labels": ["cells", "frames"]}
    result = check(load(doc), tube_graph)
    assert result.ok
    assert not any("leading axis is hidden" in w for w in result.warnings)


# --------------------------------------------------- the gate that does not run
#
# `output.width` is opt-in, and the legibility gate is the only question in
# `check` asked of some specs and not others. So its absence produced exactly the
# output its success produces: a clean green run. Six of the ten gallery specs
# were in that state, and an outside review found it by setting the field on them
# and re-running -- "they pass check only because the field that would catch it is
# absent". A confident answer to a question nobody asked is the defect this
# repository convicts other tools of, arriving in its own gate.

def test_check_says_out_loud_when_the_legibility_gate_did_not_run(
        tube_spec_doc, tube_graph):
    """The silence is the bug, so the message is the fix."""
    doc = copy.deepcopy(tube_spec_doc)
    doc.pop("output", None)
    result = check(load(doc), tube_graph)
    assert any("LEGIBILITY GATE DID NOT RUN" in w for w in result.warnings), (
        "a spec with no output.width was checked and said nothing about the one "
        "question that was skipped:\n" + "\n".join(result.warnings))


def test_not_running_the_gate_is_a_warning_and_never_an_error(
        tube_spec_doc, tube_graph):
    """OPTING OUT IS LEGAL AND MUST STAY LEGAL. A figure for a slide or a README
    has no printed size to be measured against, and making the declaration
    mandatory would turn `output.width` into a formality typed to silence a
    checker rather than a claim about where the figure is going. What is not
    legal is saying nothing."""
    doc = copy.deepcopy(tube_spec_doc)
    doc.pop("output", None)
    result = check(load(doc), tube_graph)
    assert result.ok, (
        "declining to state an output size turned coverage red: " +
        "; ".join(result.errors))


def test_the_gate_reports_the_number_when_it_does_run(tube_spec_doc, tube_graph):
    """THE PASSING CASE WAS SILENT TOO, which is the other half.

    A gate that reports only failures is indistinguishable from a gate that is
    switched off, so a green run left the reader unable to tell which they had.
    Six units is a floor nothing in the gallery misses at a generous width, so
    this asserts the report rather than the verdict.
    """
    doc = copy.deepcopy(tube_spec_doc)
    doc["output"] = {"width": "20in", "min_type": "1pt"}
    result = check(load(doc), tube_graph)
    assert result.ok, result.errors
    assert any("legibility:" in n and "clearing" in n for n in result.notes), (
        "the gate ran and cleared its floor without saying so:\n"
        + "\n".join(result.notes))
    assert not any("DID NOT RUN" in w for w in result.warnings)


def test_the_caveat_does_not_contradict_the_line_above_it(
        tube_spec_doc, tube_graph):
    """`report` printed "says NOTHING about whether ... the figure is legible"
    directly underneath a line reporting the measured point size. Both were in
    one screen of output and one of them was wrong."""
    from draughtsman.check import report

    doc = copy.deepcopy(tube_spec_doc)
    doc["output"] = {"width": "20in", "min_type": "1pt"}
    text = report(check(load(doc), tube_graph))
    assert "legibility:" in text
    assert "or the figure is legible" not in text, (
        "the caveat still claims legibility is unchecked while the report "
        "states the measured size:\n" + text)


def test_a_glyph_inside_a_box_is_warned_about(tube_spec_doc, tube_graph):
    """PROSE ON THE PAGE UNTIL `chrome` BECAME A FIELD OF A STAGE.

    The page said "never a glyph inside a box" and nothing asked. It could not:
    chrome was a property of the figure, so the only answer available was about
    all seven stages at once, and `tube` -- the model this repository was built
    for -- shipped its marks inside boxes because its last stage is words.
    """
    import copy
    doc = copy.deepcopy(tube_spec_doc)
    doc.setdefault("layout", {})["chrome"] = "box"
    result = check(load(doc), tube_graph)
    assert result.ok, "a box around a glyph is a judgement, not an error"
    assert any("glyph inside a box" in w for w in result.warnings), (
        "nothing said the boxes were around the drawings:\n  "
        + "\n  ".join(result.warnings))


def test_a_stage_that_bares_itself_is_not_warned_about(tube_spec_doc, tube_graph):
    """And the per-stage answer clears it, which is the point of the field."""
    import copy
    doc = copy.deepcopy(tube_spec_doc)
    doc.setdefault("layout", {})["chrome"] = "box"
    for stage in doc["stages"]:
        if stage.get("glyph"):
            stage["chrome"] = "none"
    result = check(load(doc), tube_graph)
    assert not any("glyph inside a box" in w for w in result.warnings), (
        "the glyph stages went bare and something still called them boxed")
