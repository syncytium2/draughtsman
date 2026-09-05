# Reproducing the 1986 cocktail-party processor — what worked and what did not

Implementation: [`examples/gallery/cocktail.py`](../examples/gallery/cocktail.py).
Tests: [`tests/test_cocktail.py`](../tests/test_cocktail.py). Paper and provenance:
[`malsburg-1986.md`](malsburg-1986.md).

**Status: the equations are transcribed and the behaviour does not reproduce.**
That is the honest state as of 2026-09-05 and it is written down rather than
tuned away.

## What is faithful

Section 3 is complete, so equations 1–8 are transcribed with every constant
carrying its equation number in the source. The module selftest pins the parts
that can be checked without running the model: eq 4's clipping, eq 6's latch in
both directions, eq 8's control function at rest and at both edges, and eq 7's
coactivity at the one case the paper states explicitly.

Two things needed judgement and both are marked `INTERPOLATED`:

- **The shape of Co(·) when a burst is not half the period.** The paper gives a
  cosine of period *T* for *T*<sub>a</sub> = *T*/2 and says the half-waves are
  otherwise "linearly stretched and compressed" so crossing-over stays at half
  overlap. This warps the cosine's *phase* piecewise-linearly. The selftest
  pins it at the stated case — it must reduce exactly to cos(2π·Δt/T).
- **A sign the paper contradicts itself on.** Eq 7 reads Δt = t*i* − t*j* with
  *i* postsynaptic; Fig. 6's axis reads Δt = t<sub>pre</sub> − t<sub>post</sub>.
  Fig. 9's caption settles the matrix convention (row *i*, column *j*, connecting
  *j* to *i*) but not the sign in eq 7.

## What does not reproduce

Two of the paper's own reported results do not come out.

**The burst period is wrong, and the paper is internally inconsistent about it.**
Section 4 reports *T* between 5.838 (n=20) and 6.971 (n=1) steps. But eq 6 gives
a lower threshold of 0.01, and eq 5 decays the gliding average by (1−δ) = 0.65
per step, so falling from *g*<sub>u</sub> = 0.4 to *g*<sub>l</sub> = 0.01 takes
ln(0.025)/ln(0.65) = **8.6 steps of refractory alone**. The two statements cannot
both hold. `test_the_papers_threshold_does_not_reproduce_the_papers_period` asserts
the inconsistency so it cannot quietly disappear.

**The model synchronises instead of segregating.** Measured over 600 steps, one
onset step of asynchrony, seed 0:

    g_l     period   antiphase   within    between   H/step
    0.01     13.98     +0.999   0.02117   0.02160   0.070
    0.03     11.00     +0.995   0.02117   0.02160   0.090
    0.06     10.03     +1.000   0.02139   0.02160   0.100
    0.10      9.98     +1.000   0.02149   0.02160   0.100
    0.15      9.97     +1.000   0.02149   0.02160   0.100

Two things to read off it. **The period floors near 10 whatever the threshold**,
so *g*<sub>l</sub> is not what sets it — raising it was the obvious fix and it is
the wrong one. And **`between` is 0.0216 = *s*<sub>0</sub>(1 + *s*<sub>d</sub>)
exactly**: every between-group synapse has run to the upper clamp of eq 8. The
cells synchronise, so Co(·) is positive for every pair, so every synapse
strengthens, so they lock harder. A runaway, and it is the thing to fix.

## Where the next hour should go

Ordered by how much they would explain, not by effort.

1. **The rise is too slow, and that sets the period.** After the refractory the
   cell restarts from *E* = 0 and grows at gain α + Σ*s* ≈ 1.118 against
   inhibition, taking six or seven steps to reach threshold. Refractory plus rise
   is the ten-step floor. The paper's Fig. 7 shows a sharp sawtooth. Something
   makes the rise faster there than here.
2. **Check the coupled sum's scale.** Nineteen neighbours at *s*<sub>0</sub> =
   0.012 contribute 0.228, which with α = 0.89 puts the loop gain above one
   before inhibition. A linearisation of the two-cell (E, H) system at these
   constants gives eigenvalues 0.874 ± 0.313i — a *damped* spiral of period 18,
   not a limit cycle at 6. Either the constants imply a normalisation the text
   does not state, or one of them is transcribed wrong.
3. **The desynchronising mechanism may need blocks that already differ.** Page 34
   describes it as a leading block switching off while *H* is still high from
   both, which slows the trailing block. That needs two blocks; from a
   symmetric start with one onset step, the excitation may pull them together
   before the lag can grow.
4. **Ask.** von der Malsburg is a senior fellow at FIAS. A model that does not
   reproduce from its own published constants is a reasonable and courteous
   thing to write to an author about, and cheaper than guessing.

## For the modernisation work

The three pieces are deliberately separable, and the failure above is confined to
the first:

- `CocktailParty.step` — eqs 1, 2, 5, 6. The oscillator. **This is where the
  reproduction gap is.** A modern relaxation oscillator (Wang's LEGION lineage,
  which is open access and has complete equations — see `malsburg-1986.md`) could
  be dropped in here without touching anything else.
- The burst detector in `simulate` — where a burst is judged to have ended, with
  Fig. 4's sub-step interpolation.
- `CocktailParty.modulate` / `coactivity` / `control` — eqs 7, 8. The plasticity.
  **This is the part that is novel and still interesting**, and it is the part a
  modern model would most likely keep rather than replace: fast weight change on
  the timescale of one stimulus, which is not what a trained network does.

`simulate(plastic=False)` freezes the coupling so the contribution of eqs 7–8 can
be measured rather than assumed.
