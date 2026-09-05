# Handoff — the von der Malsburg cocktail-party model

**Written 2026-09-05 by `draughtsman-4f`, for a session starting the new repo.**
Read this whole file before writing anything. It is one day's work and it
contains one retracted claim; which one, and why, matters more than the rest.

---

## What this is, and why it is leaving draughtsman

Christoph von der Malsburg & W. Schneider, *A Neural Cocktail-Party Processor*,
Biological Cybernetics 54(1):29–40, 1986. DOI `10.1007/BF00337113`, PMID
`3719028`.

Twenty excitatory cells, one inhibitory cell, one cell per spectral component.
Cells driven by the same sound synchronise their activity bursts; cells driven by
different sounds are pushed into antiphase. **The segregated stream is the set of
cells bursting together** — the answer is a temporal pattern, not a value on an
output line. The coupling matrix between cells is not trained; it changes *during
a single stimulus presentation*, which is von der Malsburg's synaptic modulation
and is the paper's actual thesis.

**Tony's plan is to study its function and build new versions that integrate or
replace parts with modern elements.** That is a research programme. draughtsman is
a tool for drawing nets. The work landed there because the paper and the figure
tool happened to be in the same place, which is convenience, not a reason.

---

## What exists, and where

All on `origin/main` in `draughtsman` as of `06cc790`. Take these five files.

| file | lines | what it is |
|---|---|---|
| `examples/gallery/cocktail.py` | 464 | the model, the simulation, diagnostics, selftest |
| `tests/test_cocktail.py` | 252 | nine tests; the behavioural ones characterise a gap |
| `lit/malsburg-1986.md` | 162 | provenance, the search, what is reachable |
| `lit/malsburg-1986-implementation.md` | 179 | what reproduces, what does not, and the retraction |
| `lit/README.md` | 75 | the lit-folder convention — **read the licensing rule** |

**The PDF is on disk and not in git**, at
`lit/von der Malsburg Schneider 1986 A Neural Cocktail-Party Processor.pdf`
(1.33 MB). Tony pulled it over the UMich VPN. It is gitignored deliberately: a
1986 Springer paper is not ours to redistribute, and the repo it was living in is
public with a DOI. **Carry that rule to the new repo before you carry the PDF.**

The trail is `bf774d2` (lit folder) through `06cc790` (the retraction), about
twenty commits. `git log --oneline --grep=cocktail -i` finds most of them.

---

## The state of the model, in numbers

Written in torch because draughtsman's gallery allows only torch, draughtsman and
the standard library. **In a new repo that constraint is gone** — numpy,
matplotlib and scipy are all available to you, and the diagnostics would be much
better for it. The torch dependency is still worth keeping if you ever want to
trace it.

Every constant carries its equation number in the source. Equations 1–8 are
transcribed from Section 3, not reconstructed.

### What is asserted and passing

- eq 4's clipping, eq 6's refractory latch in **both** directions, eq 8's control
  function at rest and at both edges.
- eq 7's coactivity reduces **exactly** to cos(2π·Δt/T) when the burst is half the
  period — the one case the paper states explicitly, which is what pins the
  interpolation.
- The model has **no trained parameters at all**, asserted rather than claimed.
- One traced step is **24 nodes, 0 parameters**, every `out_shape` either 20 or 1.

### What does not reproduce

Measured over 600 steps, two 10-component stimuli, one step of onset asynchrony,
seed 0:

    g_l     period   burst   antiphase   within    between   H/step
    0.01     13.98    4.48     +0.999   0.02117   0.02160   0.070   <- paper's g_l
    0.03     11.00    4.69     +0.995   0.02117   0.02160   0.090
    0.06     10.03    5.41     +1.000   0.02139   0.02160   0.100
    0.10      9.98    6.22     +1.000   0.02149   0.02160   0.100
    0.15      9.97    7.21     +1.000   0.02149   0.02160   0.100

Two things.

**The groups merge instead of separating.** `antiphase` is +1.0, meaning perfect
synchrony, where the paper reports antiphase. This is the failure.

**Every between-group synapse is pinned at the clamp.** `between` = 0.0216 is
exactly *s*₀(1 + *s*<sub>d</sub>), the upper bound of eq 8. The cells synchronise,
so the coactivity is positive for every pair, so every synapse strengthens, so
they lock harder. A runaway, and it is the thing to fix.

Burst duration at the paper's own constants is **4.48 steps against a reported
5.838** for n=20 — about 23% low. At *g*<sub>l</sub> = 0.10 it lands inside the
paper's band at 6.22 **and the desynchronisation is no better**, so matching that
number buys nothing. Do not tune toward it.

---

## The retraction, and how much to trust the rest

**I published a wrong finding and then corrected it. Read this before trusting
anything above.**

I claimed the paper contradicts itself: Section 4's "*T* = 6.971 for n=1 and
*T* = 5.838 for n=20" against eq 6's 8.6-step refractory period. I wrote it into
the implementation note and asserted it in a test.

The sentence says **"the duration of bursts"**. Fig. 6 defines the burst duration
as *T*<sub>a</sub>, so the sentence is loose with its symbol — but a loose symbol
is not a contradiction. On the plain reading there is nothing to reconcile: a
burst near 6 with a refractory near 8.6 gives a period near 15, this transcription
measures 13.98, and a research agent measuring the paper's own Fig. 8 off the page
got 15–17. **I reported that agreement as evidence of a discrepancy.**

The lesson for you: this codebase's confident statements were made by someone who
could not run the model — there is no torch on these machines, CI was the only
compute, and every behavioural sentence started life as a prediction. The
assertions in `tests/test_cocktail.py` have been through CI and are trustworthy.
The prose has been wrong once.

---

## The literature position

Established by a research agent over ~145 tool calls. Full receipts in
`lit/malsburg-1986.md`.

**There is one independent reimplementation and it hit the same wall.** Ferenc
Acs, *Semesterarbeit*, Justus-Liebig-Universität Gießen, 1994, C++, with his
thesis attached, at `github.com/ferenc-acs/Neural-Cocktail-Party-Processor`. A
real Section 3 implementation: constants verbatim, `Coact()` as three phase-warped
cosine pieces, the *G*/*N* latch, "Formel 7" in the comments.

His Diskussion reports **"unzureichende Desynchronisation großer
Neuronenverbände"** — insufficient desynchronisation of large assemblies. Small
stimuli segregated; the paper's own complex patterns gave *"nur eine sehr vage
Trennung"*. **That is exactly our failure**, reached independently in 1994. It is
invisible to citation search because he spells the author "Mahlsburg" throughout.

**It is GPL-3.0. Read it; do not copy from it into a repo you intend to license
otherwise.** This estate has already moved one model out of one repo over exactly
this (`CASCADE`, GPL-3 against BSD-3) and it was cheaper than the argument would
have been.

**One concrete lead from his code:** he computes *T* and *T*<sub>a</sub> as
running ensemble averages and feeds them to `Coact()` every step. A constant *T*
against a network running at a different period leaves `Coact` phase-misaligned on
every update — a plausible mechanism for saturating every synapse. Ours does track
them live; **audit that it tracks them correctly.**

**The published critique is entirely about scope, never reproducibility.** Wang
(1999): the model "cannot simulate the basic phenomenon of stream segregation" —
a claim about auditory streaming, not about the code working. Wang (2005) reprints
their result figure and vouches for it. **No erratum exists** (Crossref, PubMed and
a journal-wide scan all negative). The 1992 sequel (von der Malsburg & Buhmann) is
a **vision** paper with no auditory citations at all and does not supersede.

**The literature reads it as a demonstration**, and so does the paper. Section 5's
first sentence:

> The model and the simulations described are only a caricature, intended to
> communicate an idea, not to represent reality.

Section 3 adds that its details "could be replaced by others" and that the
function is insensitive to the parameters **"except where the marginal stability
of blocks is involved"** — which is precisely the regime that fails here.

---

## The leads, in priority order

1. **Schneider's dissertation.** Werner Schneider (*not* Wolfgang),
   *Anwendung der Korrelationstheorie der Hirnfunktion auf das akustische
   Figur-Hintergrund-Problem (Cocktailparty Effekt)*, Göttingen 1986, 91 pp.
   OCLC `46202873`, K10plus PPN `1651340145`. **Print only, no digital copy
   anywhere.** Held at Staatsbibliothek Berlin (Hsn 254100), Tübingen, Freiburg,
   Saarbrücken, KIT, Stuttgart. Interlibrary loan or subito; Tony has UMich
   access. The Discussion says this model segments **without** onset asynchrony
   and copes with colliding spectra, neither of which the published version does.
   **This is where the parameter derivation lives.** Tony has said: not today.
2. **Audit the running *T* and *T*<sub>a</sub>** against Acs's approach. Cheapest
   thing on this list and it targets the saturation directly.
3. **The rise is too slow and that sets the period.** After a refractory the cell
   restarts from zero and takes six or seven steps to climb back. Linearising the
   (E, H) system at the stated constants gives a damped spiral of period 18 rather
   than a limit cycle at 6 — so either a constant is transcribed wrong or a
   normalisation is unstated.
4. **The desynchronising mechanism may need blocks that already differ.** Page 34
   describes a leading block switching off while *H* is still high from both,
   slowing the trailing one. From a symmetric start, excitation may pull them
   together before the lag can grow.
5. **Write to von der Malsburg.** Still a senior fellow at FIAS. A model that does
   not reproduce from its own published constants is a reasonable and courteous
   thing to ask an author about.

---

## Where draughtsman actually came out

Worth keeping, because it is the answer to the question that started this and it
belongs in the new repo's README rather than being lost.

**draughtsman traces it fine — 24 nodes — and the trace gives a figure tool
nothing to say.** It has exactly two fact-types for a box: the shape a stage
outputs and how many parameters it holds. Parameters are zero on all 24 nodes, and
every shape is 20 or 1, because there are no channels, no spatial extent and no
projections. A faithful figure is two dozen boxes each labelled `20` and each
reading `0 params`. Compare resnet, where `1×64×8×8` and `36864 params` carry the
whole story of where a model narrows and where its mass sits.

**Neither tool nor model is broken; the vocabulary does not fit the subject.** The
paper's own Fig. 2 — twenty hexagons in a row, one below, excitatory and
inhibitory arrowheads — is a *coupling diagram*, and the coupling is both the
thing that matters and the thing that changes during the stimulus. No amount of
tracing turns that into a dataflow graph.

That has a consequence for the modernisation work: **as you replace the oscillator
with something that has real structure** — a cochlear front end, learned
couplings, channels — **the figure vocabulary starts having something to bite on.**
The 1986 model is the extreme case where it has nothing.

---

## Conventions worth carrying over

- **`lit/` with the PDFs gitignored.** `lit/README.md` has the rule and the
  reasoning. Verify the ignore with `git check-ignore` rather than trusting it;
  that is how this one was checked.
- **`murderboard/fetch_paper.py`**, pointed at the new library with
  `MURDERBOARD_LIT`. `--have` before `--need` before a download. Do not vendor it.
  Note that `web-archive.southampton.ac.uk` (Cogprints, where von der Malsburg
  self-archived) is **not** on its allowlist; the fix is to propose the host
  upstream, not to route around the check.
- **`tools/run_suite.py`** if there is no pytest on the machine. It caught two
  real failures here before CI did.
- **A claims board** if more than one session will work the repo. draughtsman's
  `CLAIMS.md` and `tests/test_claims.py` are worth copying wholesale, including
  rule 2's atomic push — `git push origin HEAD:main HEAD:<branch>` — which exists
  because not doing it turned `main` red twice in one day.

---

## What to delete from draughtsman

Once the new repo has them, in one commit with a claim:

    examples/gallery/cocktail.py
    tests/test_cocktail.py
    lit/malsburg-1986.md
    lit/malsburg-1986-implementation.md
    lit/HANDOFF-cocktail-party.md      (this file)

**Leave `lit/README.md`, `lit/_NEEDED.md` and the `.gitignore` rules.** The lit
folder is a good thing for draughtsman to keep — it will want papers for other
gallery models, and the licensing rule is worth having written down before the
next one arrives.

`lit/_NEEDED.md` currently holds two entries, both Schneider. **Move those to the
new repo's want-list** and delete them here, or draughtsman ends up carrying a
want-list for work it no longer does.

Check `examples/gallery/README.md` does not reference `cocktail.py` before you
delete it, and re-run `tools/run_suite.py`: `tests/test_counts.py` ties that
README's table to what is on disk.
