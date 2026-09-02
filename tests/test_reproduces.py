"""The committed graphs must still be what the models produce.

Figures have been asserted current since SPEC.md §6; the `graph.json` files under
them never were. That is the more load-bearing artifact — every number in every
figure is looked up from one — and until now nothing checked that any of them
still described its model.

WHY THIS IS A SEMANTIC COMPARISON AND THE FIGURE TEST IS A BYTE ONE.
DECISIONS.md correction 3: `torch.jit.trace`'s value names are not stable across
torch releases, so a byte comparison here would pin the repo to one torch and go
red on an upgrade that broke nothing. The facts — the ops, their shapes, the
parameters charged to each — are what a figure quotes and what must not move.
Rendering has no such excuse, and stays byte-exact.

Each graph carries the target and input signature it was traced from, so this
re-derives the trace from the artifact itself rather than from a list kept
somewhere that could fall behind it.
"""

import importlib.util
import json
import sys

import pytest

from conftest import EXAMPLES, ROOT

sys.path.insert(0, str(ROOT / "examples" / "gallery"))


def _importable(target: str) -> bool:
    module = target.partition(":")[0]
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _split():
    here, elsewhere = [], []
    for d in EXAMPLES:
        doc = json.loads((d / "graph.json").read_text())
        target = doc["model"]["target"]
        (here if _importable(target) else elsewhere).append((d, target))
    return here, elsewhere


REPRODUCIBLE, EXTERNAL = _split()


def _facts(doc: dict):
    """What a figure can quote, in trace order. Everything a spec references."""
    return {
        "params": doc["model"]["params"],
        "counts": doc["classification"],
        "nodes": [(n["kind"], tuple(n["out_shape"] or ()), n["params"],
                   n["module"], tuple(n["weight_shape"] or ()))
                  for n in doc["nodes"]],
    }


@pytest.mark.parametrize("d,target", REPRODUCIBLE,
                         ids=[d.name for d, _ in REPRODUCIBLE])
def test_the_committed_graph_is_what_the_model_still_traces_to(d, target):
    from draughtsman.tracing import trace

    committed = json.loads((d / "graph.json").read_text())
    fresh = trace(target, committed["model"]["input_shapes"],
                  dtype=committed["model"]["input_dtypes"])
    assert _facts(fresh) == _facts(committed), (
        f"{d}/graph.json no longer describes {target}. Re-run "
        f"`draughtsman trace {target} ...` and commit it — and remember the "
        "figure is derived from this file, so re-render too."
    )


def test_nothing_drops_out_of_this_check_silently():
    """A silent exclusion is the shape of every entry in DECISIONS.md correction
    5, and this file excludes by a rule — is the target importable — so the rule
    has to be watched rather than trusted.

    THE EXCLUSION SET IS ENVIRONMENT-DEPENDENT, WHICH IS WHY THIS IS NOT A FIXED
    LIST. `tube` is bugarach's model. bugarach is public but is not a dependency
    of this repo, so in CI it is not importable and `tube` is not re-traced; in a
    development environment that happens to have bugarach installed, it is. The
    first version of this test asserted `tube` was always excluded, which was
    false here and true in CI — an environment-dependent claim, which is its own
    small instance of the same pattern.

    So: the partition must be total, the covered set must not quietly shrink, and
    anything excluded must be excluded for the one stated reason.
    """
    assert len(REPRODUCIBLE) + len(EXTERNAL) == len(EXAMPLES)
    assert len(REPRODUCIBLE) >= 10, (
        "models have dropped out of re-tracing. Either a folder lost its "
        "models.py entry, or examples/gallery is no longer on the path"
    )
    for d, target in EXTERNAL:
        assert not _importable(target)
        assert d.name == "tube", (
            f"{d.name} cannot be re-traced here and is not the one model this "
            f"repo knows it cannot rebuild. Its target is {target!r} — either "
            "vendor the model as examples/gallery does, or say in its README "
            "why it is committed and not reproducible"
        )
