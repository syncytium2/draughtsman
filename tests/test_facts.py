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
