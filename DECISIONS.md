# Decisions — what SPEC.md left open, and where it was wrong

> **Written 2026-09-01, building the spec, and added to since.** SPEC.md §8 says
> *"decide before building, not during"*. These are the decisions, and the
> measurements behind them. It also records the places where building found the
> spec mistaken; those are first, because they are the ones that would cost
> someone a day. The later ones were found by readers of the first figure, after
> it was drawn.
>
> **The count is deliberately not stated here.** It said "three", then "four",
> and stood at "four" with seven below it — a hand-maintained number going stale
> in the document whose §5 is about hand-maintained numbers going stale. The
> corrections are numbered where they are written; that is the one place.
>
> **Not murderboarded** — internal, like the spec it answers.

---

## Corrections to the spec

### 1. The fan-out is not a fork in the graph

SPEC.md §2 and §9 describe `tube` as fanning out "into four difference-of-Gaussian
kernels *in parallel*", and §9 makes drawing that fan-out the acceptance test. The
model does that. **The trace does not record it.**

`_kernels` builds one `(4, 1, 257)` tensor and `forward` performs a single
`aten::_convolution` producing `(1, 4, 600)`. The four kernels are a channel
dimension. The only true fork in the traced graph is `bright` → {conv, cat} — the
bypass.

So the acceptance test cannot be met from topology, and a figure drawn from
topology alone would render the bank as one block: a linear stack, which is
pytorch-graph's defect arrived at from the other direction.

**What was built.** A stage may carry `lanes`, and its `count_from` is a
`{reference}` resolved from `graph.json` — never a number the agent types. The
labels are the agent's, the count is the model's, and `check` fails when they
disagree. A bank of N filters is the common case, not a quirk of this model, so
this is a first-class part of the spec format rather than a patch.

**The spec's author, on reading the result — and this belongs in the record more
than the original §2 text did:**

> *"I wrote that the four kernels 'fan out in parallel' as if that were graph
> topology. It isn't — they're one conv1d with four output channels, so it can't
> be drawn from the trace. Collapsing 26 ops into one bank box with σ₁–σ₄ as rows
> is the honest rendering, and it's a better figure than the parallel lanes I'd
> hand-drawn."*

Note what that concedes and what it does not. The **model** does fan out; §2's
description of the architecture is right. What is wrong is treating that as
something a tracer could hand you. The distinction matters for every model this
tool meets next, because it is the general shape of the problem: **a reader's
"parallel" and a graph's "parallel" are different claims, and only one of them is
in `graph.json`.** Anything that draws only what the trace forks will understate
every filter bank it ever sees.

### 2. §5's coverage check needs a stated node class

`tube` traces to 200 nodes, of which 153 are `prim::Constant`, `ListConstruct`,
`GetAttr`, int/tensor crossings and shape queries. Requiring the agent to assign
all 200 buries the signal in clerical noise, and a `spec.json` nobody can read is
not reviewable in a diff, which is the reason §6 commits it.

**What was built.** `tracing.STRUCTURAL_KINDS` and `tracing.STRUCTURAL_RULE` — the
rule in code, the verdict recorded per node, the counts reported by `trace` and
printed in the `abstract` payload. Coverage then ranges over the 47 substantive
nodes.

This is the one place draughtsman drops a node without the agent saying so, which
is why the rule is conservative and visible rather than a hardcoded skip-list.
Every op that changes a tensor's values stays. All five of pytorch-graph's
omissions are substantive under it, and `tests/test_coverage.py` asserts each one
individually.

### 3. §6's byte-equality test should split in two

§6 wants a staleness test and notes the tension: it drags a system binary into CI
in an estate where *"a skip is what silence looks like when it is being careful."*
There is a second problem it does not name — `torch.jit.trace`'s value names are
not stable across torch releases, so a byte comparison against a freshly traced
model would pin the torch version too.

**What was built.** Two tests, neither of which can skip.

- `test_render.py::test_committed_figure_is_current` renders the committed
  `spec.json` + `graph.json` and asserts byte equality. Pure Python, no torch, no
  graphviz. It fires whenever the abstraction or the renderer moves — it fired
  during this build, on a layout change, which is the behaviour wanted.
- `test_trace.py` traces a fixture model and asserts the facts *semantically*:
  every parameter attributed, shapes on every node, the concat seeing both
  branches. A torch point release that renames `%202` does not turn CI red.

### 4. A traced constant is not necessarily an architectural one

**Found by bugarach, reviewing the figure before vendoring it, 2026-09-01.** The
figure said *"widen each onset — max-pool, width 3"*, resolved honestly from
`{node:n0031.constants.kernel_size}`. Every rule in this repo was obeyed: the
agent typed no number, the reference resolved, coverage passed. **The figure was
still wrong.**

`tube` pools at `2·kmin + 1` where `kmin = int(exp(self.log_center).min().clamp(1, k))`
and `log_center` is a *trained parameter*. The centres initialise at 1/2/4/8
samples, so kmin is 1 and the pool is 3; trained they are ~4–7, which is a pool of
9–15. **The figure was true of an untrained model and of nothing else** — and it
was about to be vendored into the repository whose own generator carries the
docstring *"No fitted values appear here… this figure is true of the design."*

This is correction 1 in another currency. There the lesson was that **a reader's
"parallel" and a graph's "parallel" are different claims**. Here it is that **a
graph's "constant" and a design's "constant" are different claims**, and again
only one of them is in `graph.json`. SPEC.md's guarantee was always narrower than
it read: the agent supplies no facts, and *the facts are about one instantiation*.

**Two fixes were considered and rejected, and the reasons matter more than the
one adopted.**

*Walk the provenance back to the parameter.* Impossible, and not because of
anything in this repo. `int()` on a tensor leaves tensor-land for Python; `2*kmin+1`
is then Python arithmetic torch never sees, so the width reaches `max_pool1d` as a
bare `prim::Constant` indistinguishable from a literal `kernel_size=3`. Checked
against torch 2.13. `tests/test_trace.py::test_the_pool_width_is_baked_and_indistinguishable_from_a_literal`
pins it so the next attempt to be cleverer than the tracer finds it first.

*Keep a list of design quantities.* bugarach's own write-up names the objection
while proposing it: a list that can go stale, and it goes stale exactly when the
model moves — which is the defect the generator existed to prevent, reintroduced
one level up.

**What was built: record the tracer's own testimony.** torch already warns —
*"Converting a tensor to a Python integer… this value will be treated as a
constant"* — with a file and a line, and draughtsman was throwing it away.
`trace` now records those under `hazards` in `graph.json`. `check` then makes
quoting a `constants.*` reference an **error** while a hazard stands, until the
spec's top-level `constants` block says why that particular one is architectural.
`tube`'s spec declares two dilations (`_dilated_stack` sets `d = 2 ** i` from the
layer index, so no gradient reaches them) and quotes no pool width at all.

That is deliberately the same shape as an explicit elision: the tool cannot decide
it, so the spec states it and the statement is a line in a diff. It needs no list,
because the trace names the hazard and the check names the references.

**Note what does not catch this, because it is the near miss.** bugarach's
freshness test regenerates the figure twice and asserts the two agree, precisely
to ensure the drawing does not depend on initialised weights. It passes.
`build_tube` initialises `log_center` deterministically, so the baked 3 is
perfectly reproducible. **Determinism and architecture are different claims** —
a reproducible initialisation is still an initialisation — and a gate built for
one does not cover the other.

**One limit, stated.** A hazard is graph-wide, not per-constant, because the data
flow really is severed and pretending otherwise would be the confident-and-wrong
failure this repo exists to prevent. So the check asks about every quoted constant
in a model that bakes anything, including ones that are plainly architectural.
That is the correct side to err on, and the cost is one line of spec per reference.

**One refinement, found by running it over the gallery.** `nn.LSTM` bakes a bool
in torch's own `rnn.py` on every trace, and the first cut of this rule therefore
demanded a justification for the LSTM figure's `num_layers` — a constructor
argument, on evidence from a file the model's author never wrote. A bake inside
torch says how a *stock module was constructed*; a bake in the model's own file is
the author computing something in `forward`, which is where a fitted quantity
turns into a literal. Only the second is evidence about the figure. `_hazards`
records `internal` using the same site-packages test `_source` already uses, and
the check ranges over the model's own. The torch-side ones are still reported,
because *no hazard* and *a hazard that is not about your model* are different
facts. A rule that cries wolf on nine models in ten is a rule that stops being
read, and this one exists to be read on the tenth.

### 5. §5 is not the entire safety argument, and saying so was the risk

**Written 2026-09-02, after the fifth instance of one failure.** SPEC.md §5 says
coverage — every traced node in exactly one stage — "is the entire safety argument
for letting an agent into the pipeline." `README.md` repeats it and `check.py`
says it twice. It was true of the failure §2 measured, and five separate incidents
have now shown it is not true in general.

**Every one of the first five passed every check there was.** Three of them put a
false statement in the figure. One left the figure true but shaped so a reader
could not follow it. One was the indicator rather than the figure — which is worse
than it sounds, because the indicator is what tells you whether to trust the other
four. The distinction is kept because a summary that flattened it would be the
same kind of tidy-and-slightly-false this correction is about.

| what was wrong | the figure said | coverage said | found |
|---|---|---|---|
| A tied weight was fetched twice and charged twice | 57,100,800 parameters on a 37,184,640-parameter model | green | shipped |
| The UI counted coverage in JavaScript as well as in `check` | `48/47`, and would have said `47/47` with a node in two stages | green | shipped |
| Nothing looked at the arrows at all | Whisper's audio reaching one decoder block of four | green | shipped |
| The stage-2 payload never mentioned `layout` | every figure a ribbon, because the agent could not ask for wrapping | green | shipped |
| `{stage.out_shape}` guessed when a stage had two exits | the causal mask's `12×12` where the embedding's `1×12×384` belonged | green | shipped |
| An indexed reference handed back the batch axis the figure declares it hides | `1`, in a figure showing `30×600` | green | **in review** |
| A claim board's paths were typed by hand | *(not a figure — a session's row named three files while its branch touched nine, two of them files another session was editing)* | green | in review |
| CI ran only after code was already on `main` | *(not a figure — the suite was red for six hours and two sessions pushed onto it)* | green on the last branch that ran | shipped, for six hours |
| A claim board compared each branch's copy against itself | *(not a figure — two sessions each claimed U-Net's glyphs and built the same one twice)* | green on both branches | shipped |
| A reference resolved correctly, to the **wrong node** | `1` where the model's LSTM state counts `4` layers × directions | green | in review |

**Read the `found` column, not the row count.** Five shipped and were found by
someone tripping over the damage; two more shipped and were found later; three
were caught in review, before anything went out. The first group is evidence the
shape exists, discovered the expensive way. **The caught-in-review group is the
only evidence that writing it down does anything** — each was found by someone
applying this list deliberately to work in progress rather than by being wrong
first, and correction 6 records two further ways one feature could have gone
wrong that were closed during the build for the same reason.

Rows six and eight are the sharpest instances of the *"nothing checks the claim"*
half, and they fail in opposite directions. Six printed a value that was **true**
— the hidden axis really is `1` — and being true is what made it silent. Eight
printed a value that was **false** while every mechanism worked perfectly: the
reference resolved, coverage was green, no bare number was typed, the agent
supplied no fact. It named the wrong node. **A correct reference to the wrong
node is indistinguishable from a correct one**, and nothing in this design can
tell them apart, because the design's whole guarantee is that a resolved
reference is a real quantity from the graph — not that it is the quantity the
sentence beside it needs. Resolving is not the same as being right. It was caught
by reading the rendered text, which is the only thing that can catch it.

**Whoever adds the next row owns this paragraph.** `found` goes stale: a new
instance discovered *after* shipping does not change any existing row and quietly
falsifies the claim about what the caught-in-review group shows. It is left live
rather than hedged into something nobody has to maintain — but a live claim with
no owner is how a table becomes decoration, which is the failure this section is
about, so the owner is named. **This has already happened once**: rows seven,
eight and nine were added without the paragraph moving, and it sat asserting "the
sixth row is the only one" while three more stood beneath it.

**The sixth and seventh are not figures, and that is the point.** One is a
reference handing back an axis the figure had declared hidden; the other is not a
figure at all — it is [`CLAIMS.md`](CLAIMS.md), the board three sessions use to
say who is editing what, whose paths were a hand-typed list that nothing compared
against the branches it described. A row naming three files was made on a branch
touching nine, and two of the omitted files were being edited by someone else at
the time. The board said both sessions were clear.

Those are worth their rows because they are the first instances found in the
*process* rather than in the product, and one of them arrived in the file that
cites this correction.

**The eighth is the sharpest of all of them, because the check existed.** The CI
workflow ran `on: push: branches: [main]`, and sessions here push a branch and
then fast-forward `main` onto it — so the first run always happened *after* the
code was on `main`. It was a post-mortem attached to a branch nobody watched, not
a gate, and it reported green from the last branch that had run while `main` was
red for six hours. A check that cannot fail before the thing it guards is not a
weaker check than none; it is worse, because its green is read as evidence. Now
`on: push` unfiltered, so a branch is tested in the minute it is pushed.
The fix is the same fix: `git diff --name-only origin/main...<branch>` is the list,
computed, and the check now fails when the typed one has fallen behind it.

**They are one shape.** A quantity with a single correct value was either
**computed in two places and allowed to disagree**, or **computed in one place and
never checked at all**. Nothing about node coverage can see either. Coverage
answers *was an operation dropped*, and every one of these is a different question:
*is this number the model's, is this arrow the graph's, can this reference be
answered at all, does the agent even know this field exists.*

So the safety argument is not one assertion, it is a habit, and the habit is the
thing to state:

> **One quantity, one implementation, and something that fails when it cannot be
> answered.** Where a number has two possible sources, ask both and refuse when
> they disagree rather than picking. Where nothing checks a claim, the claim is
> decoration until something does.

That is what `check.Counts` already does for coverage, what `_traced_edges` now
does for arrows, what `repeat_counts` does for repetitions, what the payload's
field-coverage test does for the format itself, and what `{stage.out_shape}` now
does by refusing a stage with two exits. Five instances found it five times
before it was written down once.

**The wording in `SPEC.md` §5, `README.md` and `check.py` is corrected rather than
deleted.** Coverage is the *first* assertion and still the one that catches the
failure §2 measured. It was never the only one it needed to be.

### 6. A shape is not a fact to a reader who cannot name its axes

**Found by Tony, reading the shipped figure, 2026-09-02.** The first box drew
`1×30×600` under the label *"cells × frames, binary"* — three numbers, two names.
He read it as an error and asked twice: *"each number needs to be defined. box
from draughtsman says 1x30x600, then cells x frames. doesn't match."*

Every number was the model's, every reference resolved, coverage was green, and
the figure still failed at its first box. This is correction 5's list continued:
nothing had ever checked whether a drawn quantity was *legible*, because §5 asks
whether an operation was dropped.

It compounds down the figure, which is the part worth keeping. `1×1×600` at *mean
over cells* is where the ROI axis collapses and that is the single most important
thing the stage does — unnamed, it reads as a number that changed. Then `1×4×600`
and `1×5×600` have their middle axis meaning **channels** rather than cells: the
same position, counting something else, with nothing marking the change.

**What was built, and the safety property first, because it is the whole design.**
A spec may declare `batch_axis` and the figure stops drawing it — **and `check`
refuses the declaration wherever the hidden number is not 1.** An axis that is not
1 is carrying information, and hiding it would delete a number the reader needs.

That is not hypothetical on the model this was built for. `tube` reshapes to
`[30, 1, 600]` midway — cells folded *into* the batch — so a blanket "drop axis 0"
would have deleted the cell count and said nothing about it. A traced
`[1, 1, 28, 28]` has two axes of size one and only the spec's author knows which
is which. **The renderer never guesses.** It is a declaration, checked against
every shape the figure actually draws.

With it declared, the batch column of unexplained `1`s goes and two numbers stand
against two names: `30×600` → `1×600` → `4×600` → `5×600` → `8×600` → `600`.

**Correction 5 caught two things here before they shipped, which is the first time
it has been used as a checklist rather than a history.**

- `glyph.axes` indexes **positionally** into a resolved shape. Hiding the axis in
  the text but not the glyph would give one spec two numberings — axis 1 is
  "cells" to the glyph and "frames" to the label — and the picture would disagree
  with the words beside it with every check green. Both now resolve through the
  same call, so asking for an axis the reader cannot see is an error.
- The rule was checking stage text only, while `resolve` applied the hiding to the
  title as well. A claim nothing verifies is decoration; the title, subtitle and
  caption are checked too.
- **And one it did not catch, found by a reader.** `{stage.out_shape}` hid the
  batch; `{stage.out_shape[0]}` handed it straight back, and nothing objected
  because `1` is a true number. Correction 5's other half — not two
  implementations disagreeing, but one claim with a path it did not reach. An
  indexed reference to a declared batch axis is now an error, `[-3]` on a
  three-axis shape included, because comparing the literals would let the
  negative form walk past the rule. Every other index still addresses the traced
  shape: renumbering the survivors would silently move what index 1 means, which
  is the trap the convention exists to avoid.

**Adopted across the gallery, 2026-09-02, and the adoption found one more.**
Nine of the ten remaining models declare it; `lstm` is refused, and the refusal is
the best thing in this section. Its initial state is `4×1×48` and that leading 4
is *layers × directions* — a second architecture, unrelated to `tube`, where the
first axis carries information. Two independent refusals in eleven models is a
much stronger argument that the declaration cannot be inferred than `tube` alone
was. `lstm`'s caption now says so, with the 4 resolved from the graph.

**The one that nearly shipped wrong: `glyph.axes` shifts under the declaration.**
Found by draughtsman-f0 before it landed. U-Net's `axes: [1, 2]` with
`labels: ["channels", "height"]` means (channels, height) on a four-axis shape and
**(height, width)** once the batch is hidden. Both indices stay in range, so
nothing errors; every rectangle becomes a square and the constant-area finding
that figure exists for disappears. Cascade's three-axis shape fell off the end and
raised — loud at rank three, silent at rank four.

Nothing can verify the labels; they are the agent's words and only they say what
an axis means. But **negative indices do not move**: hiding a *leading* axis
leaves every trailing position where it was, so `[-3, -2]` names the same pair
before and after. The gallery's glyphs are negative now, verified by rendering
both ways and comparing the drawn rectangles byte for byte, and `check` warns when
a spec declares `batch_axis` while indexing a glyph positively — a warning and not
an error, because positive indices into the *drawn* shape are legitimate. What it
catches is the spec that had a glyph before the declaration was added.

**One implementation.** `facts.drop_batch`, reached only through `resolve`'s
`shaped()`. It fires on whole activation shapes and not on `weight_shape` — a conv
weight is `(out_ch, in_ch, k)` and has no batch axis to hide — and never on an
indexed reference, so `{stage.out_shape[1]}` cannot silently start reading a
different axis.

### 7. Resolving is not the same as being right

**Written 2026-09-02, having nearly shipped it.** `lstm`'s caption was to explain
why that one model still draws its leading axis, so it cited the number: *"{node:n0041.out_shape[0]}
on the initial state is layers × directions."* It rendered **`1`**. The state is
`4×1×48` and the 4 is what the sentence was about.

**Every rule in this repo held.** The reference resolved. Coverage was green. No
bare number was typed. The agent supplied no fact — the number came from
`graph.json`, by node id, exactly as §4 requires. And the figure said something
false.

`n0041` is a real node with a real `out_shape` whose axis 0 is genuinely 1. It is
simply not the node the sentence is about. **A correct reference to the wrong node
is indistinguishable from a correct one**, and nothing here can tell them apart,
because the guarantee this design offers is that a resolved reference is a real
quantity from the graph — never that it is the quantity the sentence beside it
needs. That second thing is a claim about *meaning*, and meaning is the half the
agent supplies.

**This is different in kind from corrections 1 through 6, and that is why it is
worth its own section.** Every one of those was a mechanism failing: a count
computed twice, an arrow nobody looked at, a field the payload never mentioned, an
index that shifted under a declaration. This is the mechanism working exactly as
specified and producing a false statement anyway. There is no check to add. §4's
guarantee is narrower than it reads, and stating the limit is the only fix
available:

> **A reference cannot be wrong about the graph. It can be wrong about the
> sentence.** The first is mechanised; the second is read, or it is not caught.

It was caught by rendering the figure and reading the text, an hour after writing
a correction about exactly this kind of confidence. The right reference was
`{stage:state.out_shape[0]}` — addressing the stage the sentence names rather than
a node id copied from the wrong row of a table.

**What follows for practice, and it is small:** when a spec's prose asserts
something *about* a number, prefer `{stage:<id>.…}` over `{node:<id>.…}`. A stage
id is the thing the sentence talks about and is stable; a node id is a positional
artifact of the trace, and getting it wrong looks exactly like getting it right.

### 8. A check that cannot see reports the thing it checks as wrong

The first seven corrections are all one shape: a quantity with one correct value,
computed twice and allowed to disagree, or computed once and never checked. This
one is a different shape and it is worth separating, because the habit that
catches the first seven does not catch it.

`CLAIMS.md` rule 2 says land the claim on `main` **before** the work, so that a
claim is visible to sessions that cannot read your branch.
`tests/test_claims.py` enforces the board, and one of its assertions resolves each
claim's branch against the refs the checkout can see.

`actions/checkout` fetches shallow and single-branch by default. The CI checkout
therefore held `main` and `origin/main` and nothing else, so **every claim ever
landed named a branch that did not exist**, and `main` went red every time anyone
followed rule 2. Run `33692848373`, 2026-09-02 22:57, on the commit
`Claim: marks on tube, block on resnet`, is the receipt: that assertion failing on
`main` while the identical tree passed on the branch. It went green again when the
work landed and the row came off, which is why it survived a full day of use.

**The failure is not that the check was wrong. It is what it said while being
wrong.** It reported a bad checkout as a bad claim. A session reading `main` would
have concluded the board was mistaken about its own contents — and a board that
appears mistaken about itself is one people route around, which is the failure the
board exists to prevent, arriving through the check meant to enforce it.

Fixed at `4849393` in two halves, because either alone rots:

- the workflow passes `fetch-depth: 0`, giving the checkout the refs;
- `test_this_checkout_can_see_the_branches_it_is_about_to_judge` fails when the
  checkout is shallow, so the next truncation says *the checkout cannot see*
  rather than *the claim is wrong*.

The first half is configuration and will not travel with the file. The second is
the part that makes the instrument honest wherever it lands, and if the board is
ever vendored into another repository it is the half that must go with it.

**The rule, stated so it generalises: a portable check must assert its
preconditions rather than assume them.** Ask what the check needs in order to see,
and make the absence of it a failure with its own message. Otherwise the check
does not go quiet — which would at least be visible — it goes confidently wrong
about its subject.

Two smaller things from the same commit, both worth keeping. The guard was
conditional in its first draft, skipping when the board was empty, and
`DRAUGHTSMAN_NO_SKIPS` failed the run for it: an empty board is not a reason to
permit blindness, only a case where the blindness costs nothing yet. And writing
this correction's own subject into `CLAIMS.md` — quoting the wrong install string
while describing it — turned `main` red inside four minutes, caught by the grep
guard in `tests/test_dist_name.py`. Both are instruments that fire without being
invoked, and on this commit two of them caught the session that was writing the
third.

### 9. A projection is a claim, and nothing was checking what it dropped

U-Net's glyph declared `axes: [-3, -2]` — channels and height — and reported the
architecture as **unchanging**. Channels double at exactly the rate height halves,
so the product is pinned by construction: C·H is 1024 at `enc1`, `enc2`, `enc3`
and `bottom`, and the rendered rectangles came out at area 149.50 to the last
digit, rotating wide-flat to tall-narrow and back.

Every check was green. Coverage complete, every drawn edge traced, every number
resolved from `graph.json`, no reference unanswerable. The figure was still
telling a reader that nothing about the tensor changed between full resolution
and the bottleneck.

The dropped axis halves too. Put it back and the volume runs **65536, 32768,
16384, 8192 and back to 65536** — the U the network is named for, and it is
invisible in *any two* of its three axes.

This is correction 5's family with one new member. There, a quantity had one
correct value and was either computed twice or never checked. Here the quantity
was computed correctly and then **projected**, and nothing asked whether the
projection kept what the reader was being shown. A glyph choosing two axes of
four is a claim about which two matter, made by the agent, checked by nothing.

**What followed.** `style: "sheets"` draws n×m×p as n flat sheets of m×p, and it
is the only style permitted a third axis. The two-axis rule was not relaxed: it
exists because the eye reads a rectangle's AREA whether or not you meant it to,
so both edges must come from one tensor — and an offset stack is read the same
way one rank up, as a VOLUME. Three axes of one tensor multiply to something real
exactly as two do. Every other style stays at two, because nothing in a rectangle
carries a third.

**Four things the build got wrong first, each caught by looking rather than by a
test, and each now checked.**

*The ceiling was stated twice.* `SHEET_MAX = 12` sat beside a minimum separable
pitch, as though a stack could fail two ways — too many sheets, or too little
depth. It cannot: a count ceiling is the pitch rule evaluated at the largest depth
the canvas allows, so the count never binds first. Measured in both canvases,
every n the cap refused the pitch had already refused; `SHEET_MAX` was unreachable
code, and it disagreed with the real ceiling by one in one canvas and by six in
the other. **Correction 5, inside a rule written to enforce correction 5.** The
pitch is now the rule and `sheet_ceiling()` derives the number the legend prints.

*The scale lied about aspect.* Each axis had its own canvas and its own maximum,
so a 64×64 map — the same number twice — drew 44 wide and 28 tall, and every
square tensor in the gallery came out at 1.45:1. One span replaced the three.
Equal values now draw equal lengths, and the widest figure in the gallery lost 142
units doing it.

*A name was painted over the drawing it named.* Text on line art is the one
collision class that is never intentional. `interface2` ships a checker for this
family and its docstring excludes exactly this case — it compares text against
TEXT, so "a label sitting on a trace with NO background box would be invisible to
this tool." Here the geometry is generated rather than measured off a raster, so
`test_no_stage_name_is_painted_over_its_own_glyph` is exact and cheap.

*And a new style was invisible to the agent.* `tests/test_payload.py` went red on
`layout.chrome`: a spec field the prompt never mentions is one no agent can
produce. That test exists because the gallery run found `wrap` in the schema and
absent from the payload. It caught the identical defect on a field added the same
afternoon, which is the argument for keeping it.

**The habit this adds.** Correction 5 says one quantity, one implementation,
something that fails. This adds: **when a figure shows fewer axes than the tensor
has, the choice of which to drop is part of the claim.** It cannot be checked
automatically — only the agent knows what a reader needs — but it can be *seen*,
by running the acceptance test against the figure that already exists rather than
building the thing that would replace it. The U-Net finding cost one afternoon of
arithmetic and no code at all.

### 10. A figure that does not know how big it will be cannot be legible

Every number in a figure could be correct, every operation accounted for, every
arrow traced — and the figure still unreadable at the size anybody sees it. That
was the state of all ten, and nothing in the tool could tell.

The cause was one line. The SVG root said:

    viewBox="0 0 1594.64 351.69" width="1594.64" height="351.69"

Unitless, which means pixels. So the figure asserted it was 1594 pixels wide and
every consumer — LaTeX, Word, a browser — scaled it to whatever fitted, taking
the type down with it. **Nothing in the source mentioned an inch, a millimetre or
a point.** `layout.wrap` looked like a size and was a count of the same arbitrary
units.

Measured at the widths a paper actually uses, with detail type at 9.5 units:

    figure         units | 3.5in  |  6in   |  7in
    lenet            782 | 3.06pt | 5.25pt | 6.12pt
    unet            1595 | 1.50pt | 2.57pt | 3.00pt
    whisper         1647 | 1.45pt | 2.49pt | 2.91pt

At a 6in double column, **not one figure cleared 6pt.** Exactly one cleared it
anywhere, at a full 7in text width.

**What was added.** `output.width` states where the figure is going and
`output.min_type` the floor its smallest label must hold there. The two fix what
a unit is worth in points, which gives a width budget:

    units_max = DETAIL_SIZE x target_points / floor_points     684u at 6in/6pt

Three things follow. The renderer emits a real physical size — `width="6in"` with
the height derived from the same scale — so a page places the figure instead of
guessing. Layout solves against the budget by wrapping the spine into more rows.
And `check` refuses a spec whose figure would print under the floor, naming the
width to aim for.

**THE TYPE IS NEVER THE THING THAT GIVES.** A figure that fits by shrinking its
labels has solved a different problem, and shrinking type is what every consumer
already does for free. The budget exists precisely because the label size is the
fixed quantity. Layout wraps harder, the graph gets narrower, and when that is
not enough the figure is refused rather than quietly rendered illegible.

**It works, and it does not work everywhere.** Solved at 6in with a 6pt floor:
`mlp` 856 -> 493 units (8.32pt), `dual` 1033 -> 560 (7.33pt), `lstm` 923 -> 653
(6.29pt). Those three now declare their size. The other seven are still over
budget — `lenet` at 782 against 684, `whisper` at 1647 — and wrapping cannot
reach it, because a row break is refused where a long edge is in flight and those
models are webbed with skips. **That is the honest state and it is now visible in
the spec rather than in a queue item**: declare an output width on any of the
seven and `check` goes red with the number.

The remaining work is not a knob. It is narrower figures: fewer detail lines, more
collapsing, or a second orientation for models whose depth is the problem.

**UPDATE, 2026-09-04, and the paragraph above is now wrong in three places.** It
is left standing because correction 5's whole value is a document catching itself,
and because being wrong about `lenet` at 782 units is the honest record of what
was known.

Six of ten specs now declare a size and clear the floor: `mlp` 493 (8.32pt),
`dual` 460 (8.92pt), `lenet` 470 (8.75pt), `lstm` 653 (6.29pt), `resnet` 516
(7.95pt) and `tube` 589 (6.97pt). `resnet` reached it partly by accident —
spelling `each edge ∝ √value` out in words made the legend sentence long enough to
WRAP instead of setting the figure's width, and it fell 160 units in a commit
about font metrics.

**The other four cannot be armed from the spec at all, and "wrapping cannot reach
it" is not quite the reason.** Swept `layout.wrap` from 680 down to 60, alone and
combined with `chrome: none` and `legend: false`, the narrowest each will go
against a budget of 684: `vae` 812, `transformer` 891, `whisper` 936, `unet` 1324.
The figures do keep wrapping — `transformer` goes from 13 rows to 16 as `wrap`
tightens — and the width stops falling anyway. `vae` is the clearest case: 876
units at every wrap value from 900 to 60, the lever doing nothing whatsoever.

The floor is structural rather than typographic. Width is set by parallel
structure that has no spine to wrap: `lanes` on the attention stages, and U-Net's
skip connections holding its encoder and decoder apart. **So `check`'s own remedy
text is wrong for these four.** It says *"wrap the spine into more rows, drop a
detail line, or collapse a stage"*; the first does not apply to a figure whose
width is not a spine, and the second is worth about 80 units where 200 to 640 are
needed. Only the third can work, and collapsing a stage changes what the figure
claims about the model — which is stage 2's judgement and not a layout fix.

`CLAIMS.md` queue item 3 says the remaining work is "narrower figures, not a
knob". For the linear figures that is exactly right. For the branched ones there
is no knob AND no narrower figure short of a different abstraction, and until now
nothing said so.

### 11. A guard that loses its subject reports all clear

Correction 8 separated one shape from the first seven: a check that **cannot see**
reports the thing it checks as **wrong**. This is the same failure in the other
direction, and it is the worse half. A check that goes confidently wrong gets
investigated within the hour, because somebody is staring at a red build with
their name on it. A check that goes confidently quiet is not investigated at all.

On 2026-09-04 five instruments in this repository did it, found by three sessions
working concurrently. Each had been written deliberately, each had a test, and
each stopped being able to fail without saying so.

| instrument | what it lost | found |
|---|---|---|
| `test_the_detector_can_fail` | ran against `dual` because the gallery happened to contain a crossing; `8e78183` moved the wrap connector into its own gutter, `dual` came out clean, and the guard could no longer tell the mutated clipper from the real one | in review, by its author |
| `draughtsman-briefing.sh --selftest` | asserted on the briefing's printed output, which stops at three rows; a third session claiming pushed the smuggled fenced row into "+1 more" | **shipped** — `main` red at `570f377`, on a commit that added one board row and nothing else |
| `_stage_boxes` | skipped stages that drew no rect, so a figure built from them had nothing to collide with and came back clean | in review |
| the crossing report | summed an edge's separate crossings into one, so a bypass and a traversal reported as the same kind of thing | in review |
| the icon bands | `0.30`/`0.20` were read off a contact sheet printing two decimals; `lstm` prints `0.30x` and is `0.2975`, so the boundary put the lowest mark anyone had confirmed READABLE on the unreadable side of its own line, by `0.0025` | in review, and it would otherwise have **shipped** |

Fixed at `8e78183`, `f78a6ce`, `7bb32db`, `ef3f340` and `c01c308`.

**Two of the five were disarmed by fixing something else.** Nobody regressed
anything. `dual` was made better and its guard went blind; a session claimed a
row, correctly, following rule 2, and the briefing's guard went blind. That is
what makes this one correction rather than five fixes: the defect is not in any
of the five instruments, it is in what they were pointed at.

**The icon case is the one to read first, because it is the only one that would
have shipped.** The other four announced themselves with a red build. This one
had every model still rendering, every existing test passing, the committed icons
byte-identical — and the CLI printing `0.30x — reads` for the very model it had
just misclassified, **because the same rounding that produced the error also
concealed it.** The number a person would have checked it against was the number
that was wrong.

Its sub-class is worth naming on its own: *rounding a value for a person to read
and thresholding it for a machine to decide are different jobs, and one value
doing both does the second one badly and quietly.* Note also how it was found —
by a throwaway script its author wrote to check their own expectations, because
there was no way to run the test they had just written. `tools/run_suite.py`
landed hours later and would have caught it directly, which is the argument for
that tool stated better than any case for it made in advance.

**The distinction that matters is not whether a check depends on external state.
It is whether the dependency is declared.** Three positions, and only the last is
the defect:

- **Controlled.** The guard builds its own subject. A fixture board, a synthetic
  spec. Nothing outside the test can move it.
- **Declared.** The guard reads the world, and an assertion says what it needs.
  `test_the_briefing_skips_the_fenced_worked_example` asserts the fenced example
  is present — *"has moved or gone, so this test no longer reproduces the case it
  guards"*. Tidy that row away and the suite goes red naming exactly what broke.
- **Incidental.** The guard reads the world and nothing records that it depends on
  what it found there. This is the only one that fails silently, and it is the
  one that cost a day.

Declared is not as good as controlled — a subject other sessions rewrite while the
test runs is a bad arrangement whatever the failure mode — but it is a design
decision, and incidental is a defect. `test_the_detector_can_fail` was incidental
and is now controlled. The briefing selftest was incidental, is now declared, and
**a fixture board it writes itself is still the right end state and is not done.**

**The remedy that generalises: assert the property the number is for, not the
number.** This is the sentence worth carrying out of all five.

    READS_AT is 0.25                     pins a value nobody can check, and is
                                         wrong the moment the corpus moves

    READS_AT has measured room on both   fails on the mistake actually available
    sides                                to make — drawing a boundary against a
                                         neighbour — and survives the right value
                                         changing

`tests/test_icon.py::test_each_threshold_sits_in_a_gap_and_not_against_a_neighbour`
requires `0.01` of measured room on both sides of each boundary and names the
neighbours when it fails. The shipped bands are `0.25` and `0.19`, sitting in gaps
`0.086` and `0.031` wide, with the measured table and the reasoning in the comment
above them in `src/draughtsman/icon.py`.

`DRAUGHTSMAN_BRIEF_ALL` is the same move: the selftest asks the parse, which is
what was being claimed, instead of the display, which was incidental to it. The
cap was moved from parse time to display time so the parse became observable
again, and the environment variable suppresses only the display.

**One note on reading the evidence, because it is easy to get wrong here.** `main`
going green after the briefing fix proves nothing: releasing any one claim drops
the board below three rows and greens it without fixing anything. The evidence
is the mutated hook exiting 1 with *"fenced example read as a live claim"* while
four rows are on the board. Anyone auditing this later should look at that and not
at the run being green — and anyone who saw it go red and green as sessions
released would reasonably have called it flaky and stopped looking, which is the
nastiest property this class has.

## SPEC.md §8, answered

### 1. Where the agent call lives — **payload in, spec out**

No HTTP anywhere in the package. `draughtsman abstract graph.json` prints the
rules, the reference grammar, the schema and a node table; an agent session or a
person writes `spec.json`. No key handling, and the tool stays usable inside a
coding-agent session, which is the primary internal use.

### 2. Graphviz — **not a dependency, in any form**

Rejected, and more firmly than §8 anticipated. Three reasons, in order of weight:

1. **§4 already forbids graphviz's output as it stands.** Ship no styling, inline
   `style=` rather than `fill=`, classes for the embedding page. Every one of
   those means rewriting the SVG graphviz hands back — so an emitter had to be
   written regardless, and going through `dot` only adds a translation step.
2. **It is the whole of §8.2's tension.** `dot` is a system binary whose output
   moves between versions. Dropping it makes the staleness test unconditional.
3. **The layout is not hard for these figures.** `layout.py` is rank by longest
   path, a dummy per rank a long edge crosses, barycentre ordering, then
   placement — about 200 lines for any DAG, not just this one.

**This is not a return to hand placement.** The objection that started this repo
is coordinates *typed per figure*. These are derived from topology, once.

One deliberate inversion of the textbook: Sugiyama straightens the dummy chains
first, so long edges run level and real nodes bend around them. A reader follows
the main path, so here a real stage is positioned by its real neighbours only, and
the skipping edge bows out of the way. That is what makes `tube`'s spine straight
and its bypass an arc. Down-weighting the dummies is not enough — any weight at
all leaves the chain a few pixels crooked, which `test_layout.py` pins.

### 3. Is the spec hand-editable — **yes, and one thing follows**

`draughtsman abstract` refuses to name an output that already exists without
`--force`. A second agent pass silently eating a human edit would make
"hand-editable" untrue in exactly the way that matters.

Edge declaration order sets lane order top to bottom. That is the one knob a human
has over vertical arrangement, and it is worth more than a better prompt.

### 4. Multiple models per figure — **partly built, and the reason changed**

§8 framed this as *"a diff view between two specs may matter more than six
separate figures"*. That is still true and still unbuilt. What was not
anticipated is why ten models want to be in one place: **not to be compared, but
to be looked at.**

`draughtsman ui examples/` discovers one model per folder and adds a picker and an
`All models` sheet that renders every figure at once. The motivation is that a
layout engine meeting ten architectures will get some of them wrong, and coverage
cannot tell you which: §5 is about operations dropped, not about pictures that do
not read. Ten figures on one screen finds in a glance what ten passing checks
conceal.

The measurement that justified it, on the first ten:

| | |
|---|---|
| coverage | 10/10 pass, every traced node in exactly one place |
| typed facts | one warning in ten specs, and it is `ε ~ N(0, I)` — a distribution's name, which is the case the warning text already excuses |
| skips | U-Net's three nested skips and ResNet's identity route cleanly, no crossings, no struck-through labels |
| **aspect ratio** | **lenet 8.1:1, resnet 8.1:1, transformer 7.8:1** |

That last row is the finding. §2 condemned torchview for a strip; at 8:1 these are
approaching the same defect from the other side, and no check catches it because
nothing is wrong with them except the shape. U-Net's own caption names the second
half of the same limitation — *"a ranked left-to-right layout gets the topology
right and cannot produce the U readers expect."* **Wrapping the spine across rows
is now the highest-value open item**, and it is a layout change, not a spec one.

## The strip, answered

Built after the gallery measured it, and the gallery README reached the same
conclusion independently: *"Layout is rank-by-longest-path with no wrapping, so
depth converts directly into width — the same defect the README criticises
torchview for, arrived at more slowly."*

Two fields, both on the spec rather than on the renderer:

```json
"layout": {"orientation": "lr" | "tb", "wrap": 760}
```

**They belong in the spec because arrangement is judgement.** A flag on `render`
would mean the committed figure came out the shape of whoever last ran the
command, and §6's staleness test would be asserting that accident. Both default
to off and are omitted from `dump()` when defaulted, so adding them changed no
existing spec and moved no existing figure — the ten staleness tests are how that
was checked rather than claimed.

| model | was | wrapped at 760 | top-to-bottom |
|---|---|---|---|
| lenet | 8.1:1 | **2.7:1** | 0.7:1 |
| resnet | 8.1:1 | **1.6:1** | 0.7:1 |
| transformer | 7.8:1 | **3.4:1** | 0.6:1 |
| unet | 6.4:1 | 4.1:1 | 0.6:1 |

Three decisions inside that are worth keeping:

**Orientation is a transpose, not a second layout.** `tb` swaps each box's width
and height on the way in and swaps the coordinates on the way out. One engine,
two readings. A second engine would drift from the first, which is the mistake
this project keeps declining to make — see also the renderer the UI shares and
the coverage count the badge does not recompute.

**A row break is illegal where a long edge is in flight.** U-Net's three skips
span the whole depth, so no boundary is free and it barely wraps — 6.4:1 to
4.1:1 and no further. That is the honest answer. Cutting a skip across a break
would not fix the shape, it would hide where the edge went. U-Net's own caption
already says a ranked layout cannot produce the U readers expect, and this does
not pretend otherwise.

**Rows are balanced, not greedy.** Greedy packing fills each row to the brim and
leaves whatever is left standing alone on the last one; ResNet's first attempt
put `class logits` on a row by itself. The packing runs twice — once to learn the
row count, once at an even share of the width — and keeps the even one if it costs
no extra row.

The wrap connector returns through a gutter to the left margin, drawn as an
orthogonal path with rounded corners rather than a curve: the return is not a
branch, it is the same line continued on the next row, and it should read as a
pipe. Reading direction stays left-to-right on every row, which a serpentine
would not.

`lenet`, `resnet` and `transformer` now carry `"layout": {"wrap": 760}` in their
committed specs — a one-line diff each, and the figures are regenerated. The
other seven are unchanged.

## Beyond §8: where the UI lives

SPEC.md does not mention a UI. It should, because §5 ends by naming a job it
cannot do — *"the names are good, the grouping is natural, the figure is
legible… those need a human"* — and leaves that human a JSON file and a
rasteriser.

`draughtsman ui` is a stdlib HTTP server on localhost and one page of vanilla
JavaScript. No dependencies, no build step, no network: a CDN font that failed to
load would resize every box the layout had already measured, and a test asserts
the page reaches nothing.

**The decision that shaped it: there is exactly one renderer.** Every picture the
UI shows is produced by `render()` — the same function the CLI calls and the same
one the staleness test asserts against. Re-implementing layout and render in
JavaScript would have been quicker to build and would have shipped a second,
divergent truth: the figure judged in the browser would not be the figure
committed to the repo, and §6's byte-equality test would be guarding a picture
nobody had looked at. `Save` therefore writes `spec.json` *and* `figure.svg`
together, and `test_ui.py` asserts the saved figure is byte-identical to the
CLI's.

The corollary is that the UI cannot be a shareable static page. That is the right
trade for a tool whose primary use is a person at the repo they are editing, and
a read-only page showing the committed SVG remains available later without any of
the drift.

**One place counts coverage.** The first cut of the UI derived its own coverage
number in JavaScript, and it read `48/47` — the numerator counting the model input
that a stage names, the denominator counting only traced nodes. It was cosmetic
here, and the objection to it was not:

> *"That indicator is the entire safety argument for letting an agent into the
> pipeline. Worth a look before it's trusted."*

Correct, and the shallow fix was insufficient. Counting distinct owned ids gives
the right total *and* would have reported `47/47` with a node sitting in two
stages — a §5 violation reading as success, with only the badge's colour
dissenting. So `check.Counts` is now the single implementation: it distinguishes
*placed in exactly one place* from *placed*, reports duplicates and unplaced nodes
separately, names the untraced model inputs rather than folding them in, and
`summary()` renders the failure into the number itself — `46/47 in exactly one
place · 1 in two`. The CLI report and the UI badge both display it. Neither
computes it.

**Edits land on disk.** SPEC.md §8.3 asks that a human edit survive regeneration.
A review surface that cannot save is a surface whose work is thrown away, so the
UI writes the files, and the raw-JSON escape hatch is always there because
`spec.json` staying hand-editable matters more than the editor being complete.

## Two things measured that the spec should carry

**Attribution needs both the module path and the source range.** Of `tube`'s 47
substantive nodes, 13 have a `scopeName` — exactly the registered `nn.Module`
children, which is all pytorch-graph could ever see. All 47 have a `sourceRange`.
Neither field alone attributes the graph; `graph.json` carries both.

**`torch.jit.trace` is deprecated on Python 3.14.** Tracing on 3.14.5 emits
`DeprecationWarning: torch.jit.trace_method is not supported in Python 3.14+ and
may break. Please switch to torch.compile or torch.export.` It works today and
produces everything above. But SPEC.md §3 rules out `torch.export` on measurement,
and this is torch telling us the other road is closing. **Nothing to do now; do
not be surprised later.** The trace layer is one module behind a stable
`graph.json` contract, which is the right shape for that risk.
