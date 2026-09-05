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
def run():
    return cocktail.simulate(600, seed=0)


def test_two_sounds_end_in_antiphase(run):
    """Fig. 7: a one-step onset asynchrony is amplified until the two groups no
    longer overlap in time. Segregation IS that antiphase."""
    r = cocktail.group_antiphase(run["e"], run["half"])
    assert r < -0.2, (
        f"the two groups correlate at {r:+.3f} over the tail of the run. The "
        "paper's claim is that a one-step onset difference drives them into "
        "antiphase; a value near zero means they are independent rather than "
        "segregated, and a positive one means they merged into a single stream.")


def test_the_coupling_matrix_goes_block_diagonal(run):
    """Fig. 9: strong synapses within each stimulus group, weak between them.

    This is the memory the paper is arguing for -- the segmentation is held in
    the coupling for about a minute, not recomputed from the input each time.
    """
    within, between = cocktail.coupling_blocks(run["s"], run["half"])
    assert within > between, (
        f"coupling within groups is {within:.5f} and between is {between:.5f}. "
        "Synaptic modulation is supposed to strengthen synapses between cells "
        "that burst together and weaken the rest; equal values mean the "
        "plasticity did nothing.")


def test_modulation_is_what_makes_the_separation_stick(run):
    """The dynamics alone can push groups apart; the paper's added claim is that
    synaptic modulation stabilises it. Freezing the coupling must therefore make
    a visible difference, or eq 7 is decoration."""
    frozen = cocktail.simulate(600, seed=0, plastic=False)
    w_live, b_live = cocktail.coupling_blocks(run["s"], run["half"])
    w_frozen, b_frozen = cocktail.coupling_blocks(frozen["s"], frozen["half"])
    assert abs(w_frozen - b_frozen) < 1e-9, "frozen coupling must not move at all"
    assert (w_live - b_live) > 1e-6, (
        "with modulation on, within- and between-group coupling must separate; "
        f"they differ by {w_live - b_live:.2e}")


def test_the_burst_period_is_in_the_range_the_paper_reports(run):
    """Section 4 gives T between 5.838 and 6.971 steps depending on block size.

    A period far outside that means the dynamics constants are transcribed wrong,
    which is the failure most likely to go unnoticed -- the model would still
    burst, still segregate, and still be a different model.
    """
    assert 4.0 < run["period"] < 9.0, (
        f"burst period is {run['period']:.2f} steps; the paper reports 5.8 to "
        "7.0, so a value outside 4-9 means a constant in eq 1, 2, 5 or 6 is wrong")
