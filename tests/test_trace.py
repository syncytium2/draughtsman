"""SPEC.md §1, §3, §4 — stage 1 produces facts, and produces all of them.

Runs against `tests/fixtures/branchy.py` rather than bugarach's `tube`, so it
needs nothing but torch — which is in the dev extra, so this never skips.
"""

import pytest
import torch

from draughtsman.facts import FactError, Graph, resolve
from draughtsman.tracing import STRUCTURAL_KINDS, trace

TARGET = "fixtures.branchy:build_branchy"
SHAPE = [1, 6, 128]


def _graph():
    return Graph(trace(TARGET, SHAPE))


def test_jit_trace_handles_the_data_dependent_int():
    """SPEC.md §3, measured: fx and export both die on a `forward` that computes
    an integer from a parameter. jit.trace does not. Any design that assumes
    `torch.export` excludes the first model this tool was built for."""
    g = _graph()
    assert g.doc["tracer"]["backend"] == "torch.jit.trace"
    assert g.doc["classification"]["nodes_substantive"] > 0


def test_fx_still_cannot_trace_this(capfd):
    """Kept so the finding is a failing test rather than a paragraph. If torch
    ever fixes this the test goes red, and that is the right way to be told."""
    from fixtures.branchy import build_branchy
    try:
        torch.fx.symbolic_trace(build_branchy())
    except Exception:
        return
    raise AssertionError(
        "torch.fx now traces a model with a data-dependent int — revisit "
        "SPEC.md §3, the tracer choice may be reopenable")


def test_every_parameter_lands_on_a_node():
    """A parameter attributed to nothing can never be drawn, so the figure's
    total would be a number the picture does not account for."""
    g = _graph()
    assert g.doc["params_fully_attributed"]
    assert sum(n["params"] for n in g.doc["nodes"]) == g.model["params"]


def test_shapes_are_present_on_every_substantive_node():
    g = _graph()
    missing = [n["id"] for n in g.doc["nodes"] if n["out_shape"] is None]
    assert missing == []


def test_the_concat_sees_both_of_its_branches():
    """The bypass. `aten::cat` takes a prim::ListConstruct, not tensors, so an
    ancestor walk that stops at non-tensor inputs loses both branches and the
    graph looks linear — silently. That is the failure mode of every tool in
    SPEC.md §2, arrived at from the other direction."""
    g = _graph()
    cat = next(n for n in g.doc["nodes"] if n["kind"] == "aten::cat")
    assert len(cat["tensor_inputs"]) == 2
    kinds = {g.nodes[a]["kind"] for a in cat["tensor_inputs"]}
    assert "aten::_convolution" in kinds        # the filter bank
    assert "aten::div" in kinds                 # the raw trace, bypassing it


def test_the_filter_bank_is_one_node_with_many_channels():
    """SPEC.md §9 wants the fan-out drawn, and the trace does not contain it as a
    fork: a bank of N filters is one convolution with N output channels. This is
    why `lanes` exists and why its count is a reference, not a number."""
    g = _graph()
    bank = [n for n in g.doc["nodes"]
            if n["kind"] == "aten::_convolution" and n["weight_shape"] is None]
    assert len(bank) == 1
    assert bank[0]["out_shape"][1] == 3         # three scales, one node


def test_classification_is_stated_and_adds_up():
    g = _graph()
    c = g.doc["classification"]
    assert c["nodes_substantive"] + c["nodes_structural"] == c["nodes_total"]
    assert c["structural_kinds"] == list(STRUCTURAL_KINDS)
    assert c["rule"].strip()
    kinds = {n["kind"] for n in g.doc["nodes"]}
    assert not kinds & set(STRUCTURAL_KINDS)


def test_module_path_or_source_attributes_every_node():
    """13 of `tube`'s 47 substantive nodes have a scope — exactly the registered
    children, which is all pytorch-graph could see. The rest are the architecture
    and are reachable only through the source range."""
    g = _graph()
    orphans = [n["id"] for n in g.doc["nodes"]
               if not n["module"] and not n["source"]]
    assert orphans == []
    functional = [n for n in g.doc["nodes"] if not n["module"]]
    assert functional, "the interesting ops have no module path — that is the point"


def test_kernel_widths_and_dilations_survive_as_facts():
    g = _graph()
    convs = [n for n in g.doc["nodes"]
             if n["kind"] == "aten::_convolution" and n["weight_shape"]]
    assert {tuple(n["constants"]["dilation"]) for n in convs} >= {(1,), (2,), (4,)}
    assert all(len(n["weight_shape"]) == 3 for n in convs)


def test_trace_is_stable_run_to_run():
    assert trace(TARGET, SHAPE) == trace(TARGET, SHAPE)


# -- SPEC.md §4, found by drawing Whisper ---------------------------------------
# The trace layer was measured on one single-input model with no shared weights.
# Both assumptions were load-bearing and neither was stated.

TIED = "fixtures.branchy:build_tied_two_input"
TIED_SHAPES = [[1, 3, 16], [1, 5]]
TIED_DTYPES = ["float32", "int64"]


def _tied():
    return trace(TIED, TIED_SHAPES, dtype=TIED_DTYPES)


def test_several_inputs_are_traced_and_each_is_addressable():
    """An encoder-decoder takes audio AND tokens. A tracer that can build only
    one dummy tensor cannot call that forward at all, which excludes the whole
    family for a reason that is structural rather than hard."""
    doc = _tied()
    shaped = [rec for rec in doc["inputs"] if rec["shape"]]
    assert [rec["shape"] for rec in shaped] == TIED_SHAPES
    assert doc["model"]["input_shapes"] == TIED_SHAPES
    assert doc["model"]["input_dtypes"] == TIED_DTYPES


def test_a_model_with_several_inputs_has_no_singular_input_shape():
    """`{model.input_shape}` on a two-input model would render a figure that
    silently describes half the input. There is no such fact, so asking for it
    must fail rather than answer."""
    doc = _tied()
    assert "input_shape" not in doc["model"]
    with pytest.raises(FactError):
        resolve("{model.input_shape}", Graph(doc))
    assert resolve("{model.input_shapes[1]}", Graph(doc)) == "1×5"


def test_one_input_still_gets_the_singular_field():
    """The common case must not pay for the other, and every call written before
    several inputs existed must still mean what it meant."""
    flat = trace(TARGET, SHAPE)
    nested = trace(TARGET, [SHAPE])
    assert flat == nested
    assert flat["model"]["input_shape"] == SHAPE
    assert flat["model"]["input_shapes"] == [SHAPE]


def test_a_tied_weight_is_counted_once():
    """Whisper's output projection IS its token embedding, so one parameter has
    two prim::GetAttr nodes. Charging both reported 57,100,800 parameters on a
    37,184,640-parameter model — a number a figure would have printed."""
    doc = _tied()
    assert doc["params_attributed"] == doc["model"]["params"]
    assert doc["params_fully_attributed"]

    embed = doc["model"]["parameters"]["embed.weight"]
    holders = [n for n in doc["nodes"] if "embed.weight" in n["param_names"]]
    assert len(holders) == 1, "the tied weight is drawn in one place, not two"
    assert holders[0]["params"] == embed

    # And it is drawn where the reader meets it. Charging the later use put
    # Whisper's 19.9M-entry table on the output matmul instead of the embedding.
    uses = [n["id"] for n in doc["nodes"]
            if n["kind"] in ("aten::embedding", "aten::matmul")]
    assert holders[0]["id"] == min(uses)


def test_mismatched_dtype_count_is_refused():
    with pytest.raises(ValueError):
        trace(TIED, TIED_SHAPES, dtype=["float32", "int64", "float32"])


def test_the_baked_python_value_is_recorded_as_a_hazard():
    """The fixture's `kmin = int(exp(log_w).min().clamp(1, k))` is the same line
    bugarach's `tube` has, and it is why the figure said "max-pool, width 3".

    torch warns that it converted a tensor to a Python integer and that the value
    "will be treated as a constant". draughtsman used to discard that warning, so
    a fitted quantity reached the figure looking exactly like an architectural
    one. It is a fact about the trace, so it belongs in graph.json.
    """
    g = _graph()
    assert g.hazards_recorded
    baked = [h for h in g.hazards if h["kind"] == "python_value_baked"]
    assert baked, "the tracer baked a Python int and graph.json does not say so"
    assert any(h["file"] == "branchy.py" for h in baked)


def test_the_pool_width_is_baked_and_indistinguishable_from_a_literal():
    """WHY THE HAZARD IS THE MECHANISM AND PROVENANCE-WALKING IS NOT.

    `2 * kmin + 1` is Python arithmetic on a value that already left tensor-land,
    so it reaches `max_pool1d` as a bare `prim::Constant` — the same node kind a
    hand-written `kernel_size=3` produces. There is nothing in graph.json to walk
    back to `log_w`. Checked here so that a future attempt to be cleverer than
    the tracer finds this test first.
    """
    g = _graph()
    pool = [n for n in g.traced if g.nodes[n]["kind"] == "aten::max_pool1d"]
    assert len(pool) == 1
    node = g.nodes[pool[0]]
    assert node["constants"]["kernel_size"] == [3]
    # nothing among its recorded producers carries a parameter
    assert all(g.nodes[p]["params"] == 0
               for p in node["inputs"] if p in g.nodes)


def test_hazards_are_stable_run_to_run():
    """The init is deterministic, so re-running proves nothing about whether a
    value is architectural — which is exactly why the hazard has to be recorded
    rather than inferred from a second trace."""
    assert trace(TARGET, SHAPE)["hazards"] == trace(TARGET, SHAPE)["hazards"]
