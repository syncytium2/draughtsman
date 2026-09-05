# Reproducing the 1986 cocktail-party processor — what worked and what did not

Implementation: [`examples/gallery/cocktail.py`](../examples/gallery/cocktail.py).
Tests: [`tests/test_cocktail.py`](../tests/test_cocktail.py). Paper and provenance:
[`malsburg-1986.md`](malsburg-1986.md).

**Status: the equations are transcribed and the behaviour does not reproduce.**
That is the honest state as of 2026-09-05 and it is written down rather than
tuned away.

## Read Section 5 before concluding the transcription is wrong

The Discussion opens:

> The model and the simulations described are only a caricature, intended to
> communicate an idea, not to represent reality.

That is the authors' own framing, and it reframes everything below. The constants
in Section 3 belong to a **reduced illustration of the Correlation Theory**, not
to a working processor. Section 3 itself says the details "are unimportant for
the realization of the abstract model described in Sect. 2 and could be replaced
by others", and that the function is "fairly insensitive to changes in the
parameters employed, **except where the marginal stability of blocks is
involved**" — which is precisely the regime that fails here. Blocks not
separating IS marginal stability of blocks.

**And the full model is somewhere else.** The references name it:

> Schneider W (1986) *Anwendung der Korrelationstheorie der Hirnfunktion auf das
> akustische Figur-Hintergrund-Problem (Cocktailparty Effekt).* Doctoral thesis,
> Universität Göttingen.

The Discussion says that model does what this one cannot: it "is able to segment
in the absence of stimulus onset asynchrony", and it handles spectra whose
components collide, which the 1986 stimuli deliberately avoid. A follow-up paper,
*A neural cocktail-party processor based on the full spectrum of auditory
qualities*, is cited as in preparation; the literature search found no trace of
it ever appearing.

Both are on the want-list in `_NEEDED.md`. **The thesis is the thing to get.**

So the reproduction gap has three candidate explanations and they are not equally
likely any more: a transcription error on my side; constants that were never the
ones that produced the figures; or a model that genuinely only works in a regime
the paper does not fully state. The authors calling it a caricature makes the
second and third a great deal more plausible than they looked an hour ago.

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

**RETRACTED: the paper is not internally inconsistent, and I said it was.** An
earlier version of this note argued that Section 4's *T* = 5.838 to 6.971 could
not be squared with eq 6's 8.6-step refractory. That took those numbers as the
*period*. The sentence says **"the duration of bursts"**, and Fig. 6 names the
burst duration *T*<sub>a</sub> — so the sentence is loose with its symbol, but a
loose symbol is not a contradiction, and I published one on the strength of it.

On the plain reading there is nothing to reconcile: a burst near 6 with a
refractory near 8.6 gives a period near 15. This transcription measures **13.98**,
and a literature agent measuring the paper's own Fig. 8 off the page got roughly
15–17. I had reported that agreement as evidence of a discrepancy.

**What remains is a real but much smaller gap.** At the paper's own constants the
burst duration here is **4.48 steps against a reported 5.838** for *n* = 20 —
about 23% low, not a factor of two.

**The model synchronises instead of segregating.** Measured over 600 steps, one
onset step of asynchrony, seed 0:

    g_l     period   burst   antiphase   within    between   H/step
    0.01     13.98    4.48     +0.999   0.02117   0.02160   0.070
    0.03     11.00    4.69     +0.995   0.02117   0.02160   0.090
    0.06     10.03    5.41     +1.000   0.02139   0.02160   0.100
    0.10      9.98    6.22     +1.000   0.02149   0.02160   0.100
    0.15      9.97    7.21     +1.000   0.02149   0.02160   0.100

Three things to read off it. At *g*<sub>l</sub> = 0.10 the burst duration is
6.22, inside the paper's reported band — but the desynchronisation is no better
there, so matching that number buys nothing. **The period floors near 10 whatever
the threshold**,
so *g*<sub>l</sub> is not what sets it — raising it was the obvious fix and it is
the wrong one. And **`between` is 0.0216 = *s*<sub>0</sub>(1 + *s*<sub>d</sub>)
exactly**: every between-group synapse has run to the upper clamp of eq 8. The
cells synchronise, so Co(·) is positive for every pair, so every synapse
strengthens, so they lock harder. A runaway, and it is the thing to fix.

## It traces, and that turned out not to be the interesting part

Run on 2026-09-05 against `build_cocktail`, six inputs, one step:

    24 nodes, 0 parameters, 22 of 24 carrying an out_shape
    aten::mul x7  add x5  clamp x2  gt x2  matmul  sub  sum  lt  and  or
    bitwise_not  to
    every out_shape is 20, or 1 for the inhibitory cell

**draughtsman has exactly two fact-types to put in a box — the shape a stage
outputs and how many parameters it holds — and both degenerate.** Parameters are
zero on all 24 nodes. Shapes never change, because there are no channels, no
spatial extent and no projections: the model is 21 units talking to each other
for a thousand steps.

So a faithful figure of this trace is two dozen boxes, each labelled `20`, each
reading `0 params`. Set that beside resnet, where `1x64x8x8` and `36864 params`
carry the whole story of where the model narrows and where its mass sits.

**Neither the tool nor the model is broken. The vocabulary does not fit the
subject**, and it is better to have demonstrated that than to have argued it —
which is what the first version of this note did.

Two smaller things fell out. The reporting code read `shape` where the key is
`out_shape`, so the first run appeared to show a trace carrying no shapes at all;
that was a bug in the reporting and it would have been published as a finding if
it had not been checked against a known-good graph. And `aten::sum` and the
scalar multiply that follows it are the two nodes with no `out_shape` — the
H-cell's reduction over all E-cells.

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
