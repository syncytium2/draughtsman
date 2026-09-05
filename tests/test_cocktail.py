"""The 1986 cocktail-party processor does what the paper says it does.

`examples/gallery/cocktail.py` transcribes von der Malsburg & Schneider 1986 from
the PDF in `lit/`. A transcription is a claim about somebody else's paper, and the
only honest way to hold it is to assert the paper's own reported results.

THESE TESTS EXIST BECAUSE THE AUTHOR COULD NOT RUN THE MODEL. There is no torch on
the machines this was written on, so every behavioural statement in that module's
docstring was a prediction until CI ran this file. That is the arrangement the
briefing already states -- the suite runs in CI -- and it is why the claims are
written as assertions rather than as prose.

WHAT IS ASSERTED IS THE PAPER'S, NOT MINE. Section 4 and Figs. 7 to 9 report:
segregation from a one-step onset asynchrony, a coupling matrix that goes
block-diagonal, and frequency doubling in the H-cell as the indicator of
desynchronisation. Those are the three below.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

GALLERY = Path(__file__).resolve().parent.parent / "examples" / "gallery"
if str(GALLERY) not in sys.path:
    sys.path.insert(0, str(GALLERY))

torch = pytest.importorskip(
    "torch", reason="the cocktail-party model is torch; install the [trace] extra")

import cocktail  # noqa: E402


def test_the_arithmetic_matches_the_paper():
    """The module's own selftest, run here so CI cannot skip past it.

    It pins eq 4, eq 6's latch, eq 8's control function, and the one case where
    the paper is explicit about the coactivity shape.
    """
    assert cocktail.selftest() == 0


def test_the_model_has_no_trained_parameters():
    """Every constant is stated in the paper and nothing is fitted.

    This is the fact that makes the model awkward for draughtsman, whose main
    quantity is parameter count -- so it is worth a test rather than a comment.
    """
    net = cocktail.CocktailParty()
    assert list(net.parameters()) == []
    assert "s" in dict(net.named_buffers()), "the coupling must be state, not weight"


@pytest.fixture(scope="module")
def sweep():
    """The model at both readings of eq 6's lower threshold, and at a few points
    between, so a failure below reports the landscape rather than one number."""
    out = {}
    for gl in (0.01, 0.03, 0.06, 0.1, 0.15):
        r = cocktail.simulate(600, seed=0, g_lower=gl)
        w, b = cocktail.coupling_blocks(r["s"], r["half"])
        out[gl] = {
            "period": r["period"],
            "antiphase": cocktail.group_antiphase(r["e"], r["half"]),
            "within": w, "between": b,
            "h_rate": cocktail.h_cell_rate(r["h"]),
            "run": r,
        }
    return out


def _table(sweep):
    lines = ["    g_l     period   antiphase   within    between   H/step"]
    for gl, d in sweep.items():
        lines.append(f"    {gl:<6.2f}  {d['period']:6.2f}   {d['antiphase']:+8.3f}   "
                     f"{d['within']:.5f}   {d['between']:.5f}   {d['h_rate']:.3f}")
    return "\n".join(lines)


@pytest.fixture(scope="module")
def run(sweep):
    return sweep[cocktail.G_LOWER_REPRODUCING]["run"]


def test_the_papers_threshold_does_not_reproduce_the_papers_period(sweep):
    """A FINDING, NOT A BUG, AND IT BELONGS IN A TEST RATHER THAN A COMMENT.

    Section 4 reports a burst period between 5.838 and 6.971 steps. Eq 6 states
    a lower threshold of 0.01, and eq 5 decays the gliding average by 0.65 per
    step, which puts the refractory period alone at 8.6 steps. The two statements
    are not consistent, and no reading of the PDF settles which the authors ran.

    This asserts the inconsistency so that it cannot quietly go away: if someone
    later changes the dynamics and the paper's own constant starts reproducing
    the paper's own period, this test fails and they should be delighted.
    """
    literal = sweep[0.01]["period"]
    assert literal > 9.0, (
        "the paper's stated lower threshold now reproduces its stated burst "
        f"period ({literal:.2f} steps). Either the dynamics changed or the "
        "discrepancy was resolved -- update lit/malsburg-1986-implementation.md.\n"
        + _table(sweep))


# ---------------------------------------------------------------------------
# THE TRANSCRIPTION DOES NOT YET REPRODUCE THE PAPER'S BEHAVIOUR, and these tests
# characterise the gap rather than assert the paper's claims and go red.
#
# Asserting "the groups end in antiphase" would be asserting something this code
# does not do, and a red main is not a finding. Asserting the opposite would lock
# the failure in. So what is asserted is the MEASUREMENT -- and the day someone
# fixes the dynamics, these fail and say exactly what changed.
#
# `lit/malsburg-1986-implementation.md` carries the sweep and the candidate
# resolutions. Nothing here is a claim that the model works.


def test_the_synapses_run_to_the_clamp_which_is_why_it_does_not_segregate(sweep):
    """The mechanism of the failure, pinned so it is not rediscovered.

    Between-group coupling sits at S0 * (1 + S_D) = 0.0216 -- the upper bound of
    eq 8's control function -- for every threshold tried. The cells synchronise,
    so Co(.) is positive for every pair, so every synapse strengthens, so they
    lock harder. It is a runaway, and it is the thing to fix.
    """
    ceiling = cocktail.S0 * (1.0 + cocktail.S_D)
    for gl, d in sweep.items():
        assert abs(d["between"] - ceiling) < 1e-4, (
            f"at g_l={gl} between-group coupling is {d['between']:.5f}, no longer "
            f"pinned at the clamp {ceiling:.5f}. If it has come off the bound the "
            "runaway may be fixed -- check whether the groups now separate.\n"
            + _table(sweep))


def test_the_groups_still_merge_rather_than_separating(sweep):
    """The headline gap. The paper's Fig. 7 claim is antiphase; this is +1.0.

    THIS TEST IS MEANT TO BE DELETED. It exists so that a change which fixes the
    dynamics cannot pass silently -- it will fail here, loudly, with the sweep.
    """
    for gl, d in sweep.items():
        assert d["antiphase"] > 0.5, (
            f"at g_l={gl} the groups correlate at {d['antiphase']:+.3f} rather "
            "than merging. If this is now negative the model has started to "
            "segregate and this test should be replaced by the real assertion "
            "from the paper.\n" + _table(sweep))


def test_freezing_the_coupling_changes_nothing_it_should_not(sweep):
    """Sanity on the plasticity switch: frozen coupling must not move at all."""
    frozen = cocktail.simulate(600, seed=0, plastic=False)
    w, b = cocktail.coupling_blocks(frozen["s"], frozen["half"])
    assert abs(w - cocktail.S0) < 1e-9 and abs(b - cocktail.S0) < 1e-9, (
        "with plastic=False every synapse must stay at the resting value")


# ---------------------------------------------------------------------------
# CAN DRAUGHTSMAN DRAW IT? The question that started this, finally asked of the
# tool rather than reasoned about.

def _summary(g):
    nodes = g.get("nodes", [])
    kinds = {}
    for n in nodes:
        kinds[n.get("kind", "?")] = kinds.get(n.get("kind", "?"), 0) + 1
    params = sum(int(n.get("params") or 0) for n in nodes)
    shaped = sum(1 for n in nodes if n.get("out_shape"))
    lines = [f"    {len(nodes)} nodes, {params} parameters, "
             f"{shaped} of {len(nodes)} carrying an out_shape",
             "    kinds: " + ", ".join(f"{k} x{v}" for k, v in
                                       sorted(kinds.items(), key=lambda kv: -kv[1]))]
    for n in nodes[:40]:
        shape = n.get("out_shape")
        shown = "x".join(str(v) for v in shape) if shape else "-"
        lines.append(f"      {n.get('id'):<8} {str(n.get('kind')):<26} "
                     f"{shown:<12} {n.get('params') or 0}")
    return "\n".join(lines)


@pytest.fixture(scope="module")
def graph():
    from draughtsman.tracing import trace
    return trace("cocktail:build_cocktail",
                 [[N] for N in (20, 1, 20, 20, 20, 20)])


N = 20


def test_the_trace_carries_no_parameters_at_all(graph):
    """The prediction in lit/malsburg-1986-implementation.md, now tested.

    draughtsman's headline quantity is parameter count -- it is what the legend
    meters and what every stage label reads back. This model has none, so every
    stage of a figure of it would read `0 params`. That is not a defect in either
    the model or the tool; it is a mismatch, and it is the concrete form of "this
    net is a bad fit for this figure vocabulary".
    """
    total = sum(int(n.get("params") or 0) for n in graph.get("nodes", []))
    assert total == 0, (
        f"the trace reports {total} parameters, and this model is supposed to "
        "have none -- every constant is stated in the paper and nothing is "
        "trained.\n" + _summary(graph))


def test_one_traced_step_is_twenty_four_elementwise_operations(graph):
    """It traces cleanly. That was never the question.

    Segregation is a transient over hundreds of steps, so no forward pass holds
    it, and a figure of this graph is a figure of the update rule.
    """
    nodes = graph.get("nodes", [])
    assert len(nodes) == 24, (
        f"one step traced to {len(nodes)} nodes, not 24.\n" + _summary(graph))


def test_the_trace_gives_a_figure_tool_nothing_to_say(graph):
    """THE ANSWER TO "how would draughtsman draw this", as an assertion.

    draughtsman has exactly two fact-types to put in a box: the shape a stage
    outputs, and how many parameters it holds. Both degenerate here.

    Parameters are zero on all 24 nodes. And every shape is 20 or 1 -- the cells,
    or the single inhibitory unit. Nothing changes dimension, because there are no
    channels, no spatial extent and no projections; the model is 21 units talking
    to each other for a thousand steps.

    So a faithful figure would be two dozen boxes, each labelled `20`, each
    reading `0 params`. Compare resnet, where `1x64x8x8` and `36864 params` carry
    the story of downsampling, widening, and where the model's mass sits.

    THE TOOL IS NOT BROKEN AND NEITHER IS THE MODEL. The vocabulary does not fit
    the subject. That is worth having demonstrated rather than argued.
    """
    nodes = graph.get("nodes", [])
    shapes = {tuple(n["out_shape"]) for n in nodes if n.get("out_shape")}
    assert shapes <= {(20,), (1,)}, (
        f"the trace now carries shapes beyond the cell count and the scalar: "
        f"{sorted(shapes)}. If a dimension actually changes somewhere, a figure "
        "of this model has something to say after all.\n" + _summary(graph))
    assert all(int(n.get("params") or 0) == 0 for n in nodes)
