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


def test_two_sounds_end_in_antiphase(run, sweep):
    """Fig. 7: a one-step onset asynchrony is amplified until the two groups no
    longer overlap in time. Segregation IS that antiphase."""
    r = cocktail.group_antiphase(run["e"], run["half"])
    assert r < -0.2, (
        f"the two groups correlate at {r:+.3f} over the tail of the run. The "
        "paper's claim is that a one-step onset difference drives them into "
        "antiphase; near zero means independent rather than segregated, and "
        "positive means they merged into one stream.\n" + _table(sweep))


def test_the_coupling_matrix_goes_block_diagonal(run, sweep):
    """Fig. 9: strong synapses within each stimulus group, weak between them.

    This is the memory the paper is arguing for -- the segmentation is held in
    the coupling for about a minute, not recomputed from the input each time.
    """
    within, between = cocktail.coupling_blocks(run["s"], run["half"])
    assert within > between, (
        f"coupling within groups is {within:.5f} and between is {between:.5f}. "
        "Synaptic modulation should strengthen synapses between cells that burst "
        "together and weaken the rest.\n" + _table(sweep))


def test_modulation_is_what_makes_the_separation_stick(run):
    """The dynamics alone can push groups apart; the paper's added claim is that
    synaptic modulation stabilises it. Freezing the coupling must therefore make
    a visible difference, or eq 7 is decoration."""
    frozen = cocktail.simulate(600, seed=0, plastic=False,
                               g_lower=cocktail.G_LOWER_REPRODUCING)
    w_live, b_live = cocktail.coupling_blocks(run["s"], run["half"])
    w_frozen, b_frozen = cocktail.coupling_blocks(frozen["s"], frozen["half"])
    assert abs(w_frozen - b_frozen) < 1e-9, "frozen coupling must not move at all"
    assert (w_live - b_live) > 1e-6, (
        "with modulation on, within- and between-group coupling must separate; "
        f"they differ by {w_live - b_live:.2e}")


def test_the_burst_period_is_in_the_range_the_paper_reports(run, sweep):
    """Section 4 gives T between 5.838 and 6.971 steps depending on block size.

    A period far outside that means the dynamics constants are transcribed wrong,
    which is the failure most likely to go unnoticed -- the model would still
    burst, still segregate, and still be a different model.
    """
    assert 4.0 < run["period"] < 9.0, (
        f"burst period is {run['period']:.2f} steps; the paper reports 5.8 to "
        "7.0, so a value outside 4-9 means a constant in eq 1, 2, 5 or 6 is "
        "wrong.\n" + _table(sweep))
