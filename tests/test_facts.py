"""SPEC.md §4 — quantities come from graph.json or they do not appear."""

import pytest

from draughtsman.facts import FactError, bare_numbers, resolve


def test_model_and_node_references(tube_graph):
    assert resolve("{model.params}", tube_graph) == "1149"
    assert resolve("{model.input_shape}", tube_graph) == "1×30×600"
    assert resolve("{node:n0116.out_shape[1]}", tube_graph) == "4"
    assert resolve("{node:n0189.constants.dilation}", tube_graph) == "32"
    assert resolve("{node:n0149.weight_shape[2]}", tube_graph) == "3"


def test_stage_references_sum_and_exit(tube_graph):
    head = ["n0149", "n0150", "n0157", "n0158", "n0165", "n0166",
            "n0173", "n0174", "n0181", "n0182", "n0189", "n0190"]
    assert resolve("{stage.params}", tube_graph, node_ids=head) == "1128"
    assert resolve("{stage.out_shape}", tube_graph, node_ids=head) == "1×8×600"
    assert resolve("{stage.nodes}", tube_graph, node_ids=head) == "12"


def test_every_parameter_is_attributed_to_some_node(tube_graph):
    """If it is not, the figure can never account for it and the total in the
    subtitle would be a number nothing in the picture explains."""
    assert tube_graph.doc["params_fully_attributed"]
    assert sum(n["params"] for n in tube_graph.doc["nodes"]) \
        == tube_graph.model["params"]


@pytest.mark.parametrize("ref", [
    "{node:n9999.params}",       # no such node
    "{node:n0116.out_shape[9]}",  # axis out of range
    "{node:n0116.nonsense}",     # no such field
    "{whatever}",                # not a reference at all
])
def test_an_unanswerable_reference_is_an_error(tube_graph, ref):
    """Never a blank. A figure with a missing number beats one with a wrong one."""
    with pytest.raises(FactError):
        resolve(ref, tube_graph)


def test_bare_numbers_seen_outside_references_only():
    assert bare_numbers("{model.params} parameters") == []
    assert bare_numbers("1149 parameters") == ["1149"]
    assert bare_numbers("kernel {node:n0149.weight_shape[2]}") == []
    assert bare_numbers("head.12") == []          # part of a name, not a fact


# --------------------------------------------------------------------------------
# `{stage.out_shape}` is only as stable as the stage's membership, and that turned
# out to matter. Found in the gallery's `repeat` work: Whisper's embedding stage
# carried two causal-mask slices, they were correctly moved upstream, and that
# changed which member was last out. The reference silently stopped meaning the
# embedding's shape and started meaning the mask's. Every reference resolved,
# coverage was green, the edge assertion was green, the repeat verified, and the
# figure stated the wrong shape. A person looking at the picture caught it.

def test_a_stage_with_one_exit_is_unambiguous(tube_graph):
    head = ["n0149", "n0150", "n0157", "n0158", "n0165", "n0166",
            "n0173", "n0174", "n0181", "n0182", "n0189", "n0190"]
    assert tube_graph.stage_exits(head) == ["n0190"]
    assert resolve("{stage.out_shape}", tube_graph, node_ids=head) == "1×8×600"


def test_exits_that_agree_are_not_ambiguous(tube_graph):
    """Two ways out is not a problem; two ANSWERS is. A stage whose exits carry
    the same shape has always had one answer and still does."""
    head = ["n0149", "n0157", "n0158", "n0165", "n0166",
            "n0173", "n0174", "n0181", "n0182", "n0189", "n0190"]
    assert len(tube_graph.stage_exits(head)) > 1
    assert resolve("{stage.out_shape}", tube_graph, node_ids=head) == "1×8×600"


def test_exits_that_disagree_refuse_rather_than_guess(tube_graph):
    """The kernel bank without the node that consumes `arange`: it now leaves
    through both the arange (257) and the convolution (1x4x600)."""
    bank = ["n0046", "n0051", "n0054", "n0058", "n0059", "n0062", "n0066",
            "n0067", "n0068", "n0070", "n0072", "n0073", "n0074", "n0076",
            "n0078", "n0079", "n0084", "n0085", "n0090", "n0091", "n0093",
            "n0097", "n0098", "n0100", "n0116"]
    assert len(tube_graph.stage_exits(bank)) > 1
    with pytest.raises(FactError) as exc:
        resolve("{stage.out_shape}", tube_graph, node_ids=bank)
    said = str(exc.value)
    assert "do not agree" in said
    assert "n0046" in said and "n0116" in said     # both candidates named
    assert "257" in said and "1×4×600" in said     # and what each would say


def test_a_membership_independent_fact_is_never_ambiguous(tube_graph):
    """`params` and `nodes` are properties of the membership itself, so they have
    an answer no matter how many ways out there are."""
    bank = ["n0046", "n0051", "n0116"]
    assert len(tube_graph.stage_exits(bank)) > 1
    assert resolve("{stage.params}", tube_graph, node_ids=bank) == "4"
    assert resolve("{stage.nodes}", tube_graph, node_ids=bank) == "3"


def test_naming_the_node_is_the_way_out(tube_graph):
    """No second spelling was added for this. The reference that names one node
    already exists, and the error message points at it."""
    bank = ["n0046", "n0051", "n0116"]
    assert resolve("{node:n0116.out_shape}", tube_graph,
                   node_ids=bank) == "1×4×600"
