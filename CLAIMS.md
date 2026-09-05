# Claims — who is holding what, and what is queued

Three Claude Code sessions have been working this repository at once. That worked
better than it had any right to, and it worked by **messaging**: every collision
was avoided by one session asking another before writing. Messages are not a
record. This file is, and unlike the messages it is **checked** —
[`tests/test_claims.py`](tests/test_claims.py) fails when a claim names a branch
that does not exist, when two open claims name the same file, when a claim points
at a path that is not there, **when a branch has touched a file its claim does not
name**, and when a claim's branch has already landed.

That is deliberate and it is the repository's own rule applied to its own working
arrangements: see [`DECISIONS.md`](DECISIONS.md) correction 5. **A claim board
that nothing checks is decoration until something does.**

## The rules, and the three near-misses that produced them

1. **Work in a worktree, never in the shared checkout.**
   `git worktree add .claude/worktrees/<task> -b <task> origin/main`.
   *Because:* uncommitted `batch_axis` work sat in the shared tree for hours. The
   session that found it had to stash and restore someone else's work to learn
   whether `main` was green, and was one `git add -A` from committing it under
   the wrong name.

   **And then it happened, so the near-miss is now a case.** On 2026-09-03
   `draughtsman-f7` edited this file in the shared checkout; `draughtsman-c9`
   committed its own row minutes later with `git add CLAIMS.md` and swept the
   other session's line in with it. `86115f8` therefore landed a claim naming a
   branch that did not yet exist, under a message about something else, and
   `main` went red on the wrong session's commit.

   Note what did NOT save anyone: it was a targeted `git add <file>`, not
   `git add -A`. Naming the file is no protection when two sessions are editing
   that file, which for this one is every session. **The trap is not only losing
   your own work — it is your work landing under someone else's name and turning
   `main` red on their commit.** Rule 6 exempts this file from being claimed; it
   does not exempt it from being edited somewhere nobody else is standing.

2. **Claim before you write, and land the claim on `main` before the work.**
   A branch's `CLAIMS.md` is a copy nobody else can read.
   *Because:* two sessions were both about to edit `render.py`'s `_box`, caught
   only by one of them asking — and later, two sessions each claimed U-Net's
   glyphs on their own branch, could not see each other, and built the same figure
   twice. The check now compares against `origin/main:CLAIMS.md`, so a claim that
   has not landed protects nobody.

   **Push the row and the branch in ONE command, or you turn `main` red:**

   ```
   git commit -m "Claim: ..." CLAIMS.md
   git branch <name>                        # AT the claim commit, not before it
   git push origin HEAD:main HEAD:<name>    # one push, both refs
   ```

   *Because:* rule 2 as written walks you into a window. The row lands on `main`,
   the branch has not reached `origin` yet, and in between
   `test_every_claim_names_a_branch_that_exists` fails — `main` is red by
   construction, for as long as it takes you to push. **This happened twice on
   2026-09-04, once to each session working that day**, and each time it was
   found by the *other* session rather than by the one that caused it.

   The obvious alternative does not work either. Pushing the branch first and the
   row second leaves a branch carrying work with no row protecting it — a smaller
   and much quieter window than the red one, and the exact thing rule 2 exists to
   close. One push closes both.

   Cutting the branch *before* the claim commit is the third trap: it is then
   `ahead=0`/`behind=1` the instant the row lands, which `_spent()` reads as
   landed-and-unreleased, and rule 4's check fires on a claim whose work has not
   started. Cut it at the claim commit.

   **None of this is visible locally.** The branch is fine, the worktree is fine,
   `git log` is fine. Only `origin` knows, and only CI asks. The instinct after
   being burned is to add a local check; a local check cannot see this.

3. **A claim names paths, not intentions.** "the layout" is not a claim;
   `src/draughtsman/layout.py` is.
   *Because:* `check.py` was touched six times today and `test_coverage.py` five,
   by two sessions, and two of those collided as append-append conflicts in the
   same test file.

4. **Release the claim in the LAST COMMIT BEFORE you land, not after.** There is
   no ordering of "land, then release" that keeps `main` green: the instant the
   branch merges, its row names landed work and the check fires on `main` until a
   second push removes it. Released on the branch, `main` is green at every
   instant. Found by `draughtsman-f0` running the sequence end to end.

5. **A row is only as good as its paths, and paths are typed by hand.** So the
   check computes `git diff --name-only origin/main...<branch>` and fails when the
   branch has touched a file the row does not name.
   *Because:* the first version of this file trusted the typed list. A claim
   naming three files was made on a branch that touched nine, and two of the six
   it omitted were `render.py` and `abstract.py` — `render.py` being a file
   another session was drawing in at that moment. The board would have said both
   were clear. **That is this repository's own subject arriving in the file that
   argues about it:** a hand-maintained list, holding a value with one correct
   answer, going stale exactly when it mattered. Found by
   `draughtsman-e9`, whose row it was.

6. **This file is never itself claimed.** Rule 2 says claim before you write, so
   a session holding `CLAIMS.md` would make every other session edit a file it
   does not own in order to claim anything. Edits here are one row and are
   expected to be concurrent. The check exempts it.
   *Because:* the first version of this board claimed itself, which made the file
   that exists to prevent collisions the most contended file in the repository.
   Found by `draughtsman-f0`.

7. **A session that does not appear here is not accounted for.** One session
   worked this repo for eighteen hours before the other two knew it existed. This
   is the one rule nothing can check.

## Open claims

| session | branch | paths | since | doing |
|---|---|---|---|---|

An empty table is the correct state and a legal one — an earlier version of the check required a row
and would have gone red forever the moment the last session released, which is
[`DECISIONS.md`](DECISIONS.md) correction 5 arriving in the check meant to enforce
it.

A real claim that was held and released, kept as the worked example — it is inside
a fenced block, so the check reads it as documentation rather than as a live row:

```
| `draughtsman-e9` | `name-every-axis` | `src/draughtsman/facts.py`, `src/draughtsman/spec.py`, `DECISIONS.md` | 2026-09-02 | Naming shape axes so a reader can tell which is which |
```

**Expired**, and instructive twice over: it shows a claim naming its paths rather
than an intention, which is rule 3 — and those three paths were not all of them.
The branch touched nine files. Rule 5 exists because of this row.

## Queue — unclaimed, roughly in the order they are worth doing

Take one by adding a row above and saying so. Nothing here is assigned.

**0. THE PATH TO PUBLIC — the standing list.** *Tony's, and it is the goal
everything below is sequenced against.* The repository is private; the
tonydefazio.com tile is built, is the first card, and its deploy gate is
`gh repo view syncytium2/draughtsman --json visibility` returning PUBLIC. So this
list is what stands between here and that flip, in order:

- [x] **The licence blocker.** CASCADE was GPL-3.0 against this repo's BSD-3.
  Moved to `haruspex` at its `8520125`; gone from here at `3652d81`.
- [x] **The things a stranger hits first.** The name that installed someone
  else's package, a Cyrillic word in an English comment, a jab at a named
  company, a numbering gap that looked like a mistake.
- [x] **Stop counting the models in prose.** Done. The gallery table is the
  list, `tests/test_counts.py` compares it with the directories both ways, and
  a prose count of models is now refused rather than remembered.
- [x] **The editorial pass.** Done for `README.md` and `SPEC.md`, by running the
  murderboard (`syncytium2/murderboard`) rather than by editing to taste — process
  read in place, roster derived, every role accounted for, coverage gate green,
  nothing vendored. Vendoring was considered and declined: it is eight files of
  another project's harness in a repository whose pitch is that it has almost
  none, and the value was the review, not the harness. `DECISIONS.md` is still
  outstanding — it is held on `volume-glyph`, and its two findings are below.
- [x] **`CONTRIBUTING.md`.** Done at `d0dd7f1`. One page, leading with the rule
  the repository is built on rather than with formatting preferences.
- [x] **Two stories into the README.** Done at `d0dd7f1`. The CI blindness and
  the `glyph.style` gap now sit immediately before "Working on this", so a reader
  meets them before the section explaining that several sessions wrote this.
- [x] **PyPI prep.** Done at `d0dd7f1`. `project.urls`, a stated version policy,
  and all twelve README links made absolute — PyPI renders the readme with no
  repository around it, so every relative one died there. That made the repo URL
  a quantity kept in two places, so `tests/test_readme_links.py` ties them and
  also fails on a link pointing at a path this repository does not have.
- [x] **Prune the merged branches.** Done by Tony, 2026-09-03. Sixteen deleted
  (the count here said eleven and was stale), each verified at zero unmerged
  commits against `main` first, so nothing was lost. `origin` now carries
  `main` alone.
- [x] **The flip.** PUBLIC as of 2026-09-03.
  `gh repo view syncytium2/draughtsman --json visibility` returns `PUBLIC`, which
  is the tonydefazio.com tile's deploy gate. All nine unique absolute links in
  `README.md` were then fetched and returned 200 — a check that could not be made
  while the repository was private, because every one of them 404s either way when
  it is.
- [x] **Zenodo for a DOI.** Done 2026-09-03. Concept DOI
  `10.5281/zenodo.22286341`, which always resolves to the newest release; the
  version DOI for `v0.1.1` is `10.5281/zenodo.22289006`. The badge and
  `CITATION.cff` both cite the concept one, and `tests/test_readme_links.py`
  refuses them disagreeing.

  **Two things that cost a release to learn.** Zenodo reads `CITATION.cff` from
  the TAGGED snapshot, so a metadata correction landed on `main` after a release
  never reaches the archive — `v0.1.1` exists because `v0.1.0` carried the wrong
  author initials. And `v0.1.0`'s webhook event was ACCEPTED (HTTP 202) and then
  never completed its archive; an accepted event is not a completed deposit, and
  a new release re-triggers processing, which is the remedy.


- [x] **THE UPLOAD. It was never on this list, which is why it never happened.**
  **Done 2026-09-05: `draughtsman-nn` 0.1.2 is on PyPI.**
  Everything above it was read as covering it: the name, the URLs, the version
  policy and the absolute README links landed at `d0dd7f1` under "PyPI prep", the
  repository went public, Zenodo minted a DOI — and `pip install draughtsman-nn`
  returned a 404 for every one of those days. There was no build step and no upload step
  anywhere in the repository. A list that sequences everything against the flip to
  public can still omit the one item a stranger actually needs.

  The machinery is done and checked (`8db7e23`): `.github/workflows/publish.yml`
  builds on a `v*` tag, refuses to upload unless the tag is the version in the
  built wheel, and publishes with a trusted publisher so no token is stored here.
  The version is now written in one place, `src/draughtsman/__init__.py`, and the
  tree is at `0.1.2` — not `0.1.1`, because `v0.1.1` is already a tag, a release
  and a Zenodo deposit taken at `577bf92`, whose snapshot says `0.1.0`.

  **What it took, recorded because the machinery was never the hard part.** The
  account did not exist, and the registration flow defeated three attempts in
  Safari: hCaptcha escalated to two puzzles, then the EDGE bot-challenge — a
  separate layer that does not know the form exists — intercepted the POST, and
  since a challenge can only replay a GET, the submitted data was gone and
  Warehouse re-rendered an empty form with no error. It went through first try in
  Firefox. Safari's shipped defaults were the cause; nothing was installed.

  Released from tag `v0.1.2` at `10f1da6`, run 33995160924, build 15s + publish
  25s. Verified from outside rather than from a green tick: `pip install
  draughtsman-nn --no-cache-dir` into an empty virtualenv installs 0.1.2 and
  `draughtsman --version` prints 0.1.2. Both files carry PEP 740 attestations,
  signed through Fulcio and logged in Rekor — and note that the JSON API's
  `urls[].provenance` field read as `null` for both while the attestations
  existed. `https://pypi.org/integrity/<name>/<version>/<file>/provenance` is the
  endpoint that answers; the first check said "no attestations" and was wrong.

  `README.md`'s install block now leads with `pip install draughtsman-nn`; the
  editable installs moved below it, labelled as the way to work on the project
  rather than the only way in. The sentence "It is not published yet" is gone.

- [ ] **JOSS, if wanted — and it is not an alternative to the above.** Zenodo
  archives and mints a DOI in a day with no review; JOSS is peer review that also
  mints one, takes months, and expects a submission to point at an archived DOI'd
  version. So Zenodo is a prerequisite rather than a substitute. What this repo
  still lacks for it is `paper.md` and a statement of need; licence, tests, docs
  and `CONTRIBUTING.md` are done. The venue precedent is already cited in
  `SPEC.md` §2 — nn-SVG is LeNail (2019), *JOSS* 4(33):747.

Not on this path and deliberately after it: JOSS, the publication-grade output
work (item 3), the slab mode, and the Rupprecht email. None of them gate the flip.

**0e. HANDOFF — the gallery is clean, and three guards were the real work.**
*Written 2026-09-05 by `draughtsman-c4`, replacing 0d, whose technical item is
done. Numbers below are generated: `tests/test_handoff.py` re-runs the command and
fails when the output moves.*

```verified
$ python3 tools/edge_collisions.py examples/gallery/*/figure.svg examples/tube/figure.svg
dual: clean
lenet: clean
lstm: clean
mlp: clean
resnet: clean
transformer: clean
unet: clean
vae: clean
whisper: clean
tube: clean
```

**WHAT CLOSED.** Every edge-through-a-box in the gallery, which was 0d's item 1.
It was three faults wearing one number:

- The detector **summed** an edge's separate meetings with a box, so a bypass arc
  clipping two corners reported as one deep crossing and read like a traversal.
  Splitting it into contiguous runs turned six rows into nine and made the shapes
  legible — the pairs were symmetric to the unit (26/26, 27/27, 70/70), which is
  the signature of an arc bowing under a box.
- **A bypass now has the width of the rank it crosses**, so it runs level beneath
  the stage rather than dipping to a point at its centre. Cleared eight. Depth was
  the wrong lever and was tried first: `DUMMY_H` 12→44 moved transformer 21%→14%
  and cleared nothing.
- **A wrap connector returns through the gutter reserved for it.** `GUTTER = 34.0`
  is commented "the lane a wrap connector returns through" and `row_gap` reserves
  it between every row — the space existed and the connector was taking the
  midpoint between its two endpoint boxes instead. Cleared the ninth, `dual`, the
  one Tony found by looking.
- **A stage that draws no rect is now measured** through the `data-box` the
  renderer already writes. lenet had been offering 4 boxes for 9 stages, so those
  figures came back clean for want of anything to collide with. 85 of 85 now, and
  still clean — the gallery was genuinely clean, not merely unexamined.

No figure changed size in any of it.

**THE PATTERN, and it is the session's real finding.** Five checks went blind in
one day, each reporting all clear rather than reporting that it had stopped
looking: the summing detector; a mutation guard anchored to `dual` that fixing
`dual` disarmed; `_stage_boxes` skipping what it could not parse; the briefing's
guard, which needed the live board short enough for a smuggled row to print and
went blind the moment three sessions claimed at once, turning `main` red for
everyone; and icon bands read off a contact sheet rounded to two places, putting
the boundary 0.0025 under the lowest mark confirmed readable. `draughtsman-4f`
holds `correction-11` in `DECISIONS.md` for the class. **A check whose sensitivity
rides on incidental state reports all clear when it loses it.**

**`tools/run_suite.py` EXISTS NOW, and it is why three of those were caught here
instead of by CI.** There is no pytest on these machines — test modules cannot even
be imported — so a session could run no test locally and learned about mistakes
from a red `main`. That happened to me once. It runs 517 of 526 collected tests,
one at a time by node id, never prints a bare PASS, and states what it could not
run. **CI is still the verdict.**

---

**STILL OPEN, carried forward from 0d.**

**0e. `whisper/compare.svg` — three defects of one family, and the family is the
finding.** *Written 2026-09-05 by `draughtsman-a4` as a handoff; two of the three
are not started.* The figure is
[`examples/gallery/whisper/compare.svg`](examples/gallery/whisper/compare.svg),
generated by [`tools/compare_stack.py`](tools/compare_stack.py) — torchview's own
layout with each stage drawn as a region around the nodes it covers. It needs
torch, torchview and graphviz to regenerate, none of which CI has, so the artifact
is committed and `--selftest` checks it by reading the geometry back out of the
file. **To regenerate:** make a venv, `pip install torch torchview`, then
`<venv>/bin/python tools/compare_stack.py`.

All three are *did two things land on each other*, which is the family filed with
armory on 2026-09-05 as its findings 11 and 12 (armory `2bd658c`): interface2 had
already answered it three times, in pptx, pdf and MATLAB, and this repository built
a fourth and a fifth knowing of none of them.

- [x] **Box against box.** Two regions overlapped by 5.0 × 65.7 and 1.3 × 18.7
  units. Found by Tony on a phone, zoomed in — by no check here. The cause was a
  fixed 3-unit pad closing a gap of about one unit between the two spines. Fixed at
  `9ca4019`: the pad is capped at the room actually available, the tool refuses to
  write an overlapping figure, every region carries `data-stage` so the committed
  file can be measured without regenerating it, and `tests/test_tools.py` slides a
  region 40 units and requires the selftest to go red.

- [ ] **Line against box — three of eleven leaders cross a region they do not
  belong to.** Measured rather than estimated:

  ```
  leader 4 -> embed;  leader 6 -> audio, dcross;  leader 8 -> drest
  ```

  This is `tools/edge_collisions.py`'s exact subject and that tool cannot run here:
  `compare.svg` has no `ds-stage` groups. **The fix is routing, not nudging.** Each
  leader now runs straight from its region's right edge to its label; a horizontal
  stub to a shared gutter and then a vertical drop removes the crossings by
  construction. Do the routing first and have the checker assert zero afterwards,
  the way the overlap one does.

- [ ] **Our arrows are not in this figure at all.** All 96 arrowheads are
  torchview's; draughtsman's stage-to-stage edges are absent, so the composite says
  which nodes each stage covers and not how the stages connect — no dashed
  cross-attention path, no two spines meeting. Tony noticed this before any check
  did. **Editorial call, not a defect to fix quietly:** drawing `spec.json`'s edges
  down the label column is honest and adds ink to a figure that is already 520 ×
  1730, and the connectivity is one screen up in the banner figure.

- [ ] **The caption does not say that horizontal distance means nothing.** Vertical
  position is graphviz's rank, which is execution depth and is a real quantity;
  horizontal position is where graphviz packed two spines and carries no claim.
  Both scales are isotropic — `0.4248` on the wrapper, `0.704596` inside
  torchview's own SVG — so nothing is stretched, but a reader has no way to know
  which axis to trust, and this page's whole argument is that a figure states what
  it measures. One sentence in `build()`'s caption.

**Two things wait on other people and should not be re-derived here.** The armory
submission (findings 11 and 12, `2bd658c`) is with a receiving session there; it
asks for a rescan rather than a patch and names the two tools vendored FROM armory
that must be excluded rather than collected. And the darkroom claim for the Whisper
figures is bugarach PR #482, unmerged — the five files are written to that mount and
the board block says in terms that a claim which has not landed protects nobody.


**1. Four specs declare no size, and they are the hard four.** transformer 1277u
(3.21pt at 6in), unet 1607u, vae 1392u, whisper 1647u, against a 684u budget.
`draughtsman-4f` established these need fewer detail lines, more collapsing or a
second orientation — not a wrap value. And queue item 3's 3.5in target is
unreachable while `CAPTION_MIN_W = 460.0` floors every captioned figure. **Start
at the caption floor, not the layout levers**, and decide whether that target
survives at all.

**2. `examples/tube` mis-names its own axes, and it blocks another repo.**
bugarach's `docs/DEPLOY_HOLD.md` holds their publish on a revised figure from here,
and their architecture doc is vendored from `examples/tube/spec.json`. **It needs a
decision before it needs code:** the legend takes its axis name from the first
glyphed stage (`render.py:470`), and tube's middle axis genuinely changes meaning
partway through — cells for the first three stages, channels from the kernel bank
on. Either the legend learns to name both, or the figure stops claiming one name
for an axis that has two. Renderer change versus editorial call.

**3. Icon mode post-processes rather than re-laying out**, so a boxed figure
carries more empty box than it needs. Nothing checks that an icon is legible *as a
mark*; that judgement is still a person's. `draughtsman-b2` has been in
`icon-legibility`.

**4. The board cannot be dialled.** A reader cannot message the session holding a
row: the board tag and the routable `ListAgents` name are different strings and
nothing maps them. Adding the routable name to the row shrinks it. (Sometimes they
coincide — mine did — which makes it worse, not better.)

**5. Tony's, not a session's.** tonydefazio.com is ahead of a public origin with
deploy withheld; `draughtsman.tonydefazio.com` had no certificate because the
domain was set by committing a `CNAME` rather than through Pages settings; this
repo's Pages site loads Google Fonts, the only external request in a repo whose
pitch is zero dependencies; the card can now carry a real figure since `--icon`
exists. Plus: email Peter Rupprecht about CASCADE (an offer now, nothing blocked),
optionally ask Kyle Fuller for the PyPI name, the outside-reader pass on
`examples/gallery/README.md`, and no issue template.

**6. What the night taught, and it is not a task.** Every defect that mattered was
found by *looking*: edges through stages, from a screenshot; arrows pointing at
nothing, by rasterising an icon; an icon cropped by exactly its `ds-body`
transform. This suite has 500-odd assertions and was green through all of it.

    rsvg-convert -w 1260 -h 312 -b white FIG.svg -o FIG.png

and then open the PNG. Both flags together stretch to fit, so that exact line is
for an icon at 3x; for a full figure pass `-w` alone. A session that has only
measured a figure has not seen it.

**0c. Denser figures for the web page, without losing legibility.** *Was a
handoff; superseded by 0e and kept as backlog, because its measurements are still
the only ones anyone has taken of the gap levers.*
*Written 2026-09-03 by `draughtsman-c9` at the end of a long session. Everything
below is measured, not estimated.*

**Where this came from.** The project site draws the gallery figures at the scale
their own labels require, so a figure's body type matches the page's body type.
That works, and it made the next problem obvious: the figures are mostly empty.

    boxes cover 16-23% of the canvas   (dual 23.3%, whisper 20.1%, vae 16.7%)

Three of the ten measure 0.0% there, and that is the metric failing rather than
the figures being emptier: `lenet`, `resnet` and `unet` set `layout.chrome:
"none"` and draw no box rectangles for it to find. **Fix the metric before
trusting it** — it should measure drawn ink, not `<rect>` elements.

**The levers, and what each is worth.** `layout.build` takes `hgap=54`,
`vgap=26`, and `render` pads boxes at `PAD_X=12`, `PAD_Y=9`. Measured by
rendering the gallery with them changed:

    model        now   hgap36/vgap18   + pad 8/6
    dual         560            506         482     -14%
    lstm         653            581         557     -15%
    whisper     1647           1521        1457     -12%
    unet        1595           1451        1451      -9%
    mlp          493            679         655     +33%   <-- got WORSE

**Read the mlp row before starting.** Tighter gaps change what the wrap solver
chooses, so a figure can come out *wider*. Any change here has to be measured
across all ten, not on the one being looked at — and `tests/test_layout_shape.py`
already pins aspect ratios that will move.

**What it does not fix.** 10-15% is not the 2x `unet` needs to reach the 684-unit
budget at 6in. Density is worth doing for the page and for slides; it is not the
answer to queue item 3. That answer is fewer detail lines, more collapsing, or a
second orientation.

**Do not trade legibility for it.** `tools/measure_type.py` reports what type
actually renders at, for any width, and exits 1 under a floor:

    tools/measure_type.py --print 6in --floor 6pt examples/gallery/*/figure.svg

Run it before and after. The type size is the fixed quantity — that is
`DECISIONS.md` correction 10, and three separate failures this evening came from
believing an eye over that arithmetic.

**One loose end.** The SVG declares `width="6in"` for print, and a browser
honours it at 576px — so a web page must override with its own width or the
figure renders at 1.03x and the labels come out at 9.8px. The site does this; any
other consumer will hit it. Worth a line in the README.

**0b. What the murderboard found and nobody has fixed.** The run records lived in
a session scratchpad, which dies with the session; this is what survived it.

**On `DECISIONS.md`. Unclaimed as of 2026-09-03 evening** — this said "it is
`draughtsman-c9`'s", which was true when written and stopped being true when that
row was released. Anyone may take it.
- The wrap table is **stale, and more so than this entry says**. It claimed resnet
  1.6:1 and unet 4.1:1 against 1.3:1 and 5.2:1 rendered — and every figure has
  since been re-rendered twice more, for two type sizes and for one shared glyph
  scale, so the ratios have moved again. It cannot be recomputed in full: the
  "was" column describes figures that no longer exist. **Date it as a measurement**
  rather than repair it.
- ~~**U-Net's caption asserts a shape the figure cannot show.**~~ **Fixed
  2026-09-03.** The finding was right and it turned out to be the largest one of
  the day: channels × height is pinned at 1024 across all four encoder stages *by
  construction*, so the figure reported the architecture as unchanging while every
  check stayed green. The U lives in channels × height × width. `style: "sheets"`
  draws the third axis, the caption no longer claims the two-axis product carries
  anything, and it is written up as `DECISIONS.md` correction 9.

**On the argument, and it is Tony's call:**
- **The agent's own quality is stated nowhere.** The README says an agent supplies
  the abstraction and that coverage proves nothing was dropped, but never how good
  the groupings were or how many specs needed correcting. For a reader evaluating
  agent-assisted work that is the number they will want, and it is the one number
  this repository does not have.
- `SPEC.md` §2 is still an argument carried by a table. The two images now in the
  README would serve it too.

**Residual `⚠`, carried by both runs and recorded in `SPEC.md`'s header:**
- §2's measurements were taken on a model that is not in this repository, so a
  stranger cannot verify them from a clone.
- Role 2 ran **single-pass**, which the process says is the one role that may never
  be collapsed for a deliverable claiming novelty — a self-review inherits the
  drafter's search history and stops in the same place. It still surfaced one gap:
  the claim that the judgement step is "the only missing piece" ships without
  acknowledging that LLM-in-the-loop diagram generation is published work
  (Paper2SysArch, arXiv 2511.18036). CHI/VIS were not searched.
- **Nobody has asked any of the five tools' authors anything.** The process calls
  correspondence the cheapest check in the document. It has not been run.

**1. The outside-reader pass.** *Tony's call, not a session's.* `SPEC.md` and
`DECISIONS.md` both carry "not murderboarded — an internal spec, not a document
for outside readers". `examples/gallery/README.md` does not and should. This
matters more than it did this morning: `DECISIONS.md` correction 5 is now the
load-bearing document in the repository and it is written for the three sessions
that produced it.

**2. `lanes` can claim a parallelism that is not there.** The last open technical
gap. A stage that is four blocks in *sequence* can carry lane labels asserting
parallelism, and nothing verifies that a lane count is attached to a single
sublayer. Two sessions have agreed it should stay open and honest rather than get
a heuristic — so the first move is a design, not a commit.

**3. NO FIGURE IS LEGIBLE AT A JOURNAL COLUMN WIDTH — the mechanism is now
built; seven of ten figures still miss it.** `output.width` and `output.min_type`
state where a figure is going and what type it must hold there, layout solves
against the budget, and `check` refuses a figure that would print under the floor.
`mlp`, `dual` and `lstm` declare 6in and clear 6pt. The other seven are over
budget and do not declare a size — declaring one turns `check` red with the
number. What remains is narrower figures, not a knob. See DECISIONS.md correction
10. Original measurement: Measured by
`draughtsman-65` and reproduced independently. Detail text is 9.5 units; figures
are 750–1737 units wide, so placing one in a 3.5in column scales the type to
between 1.4pt and 3.2pt. **Nothing clears 6pt at 3.5in.** At the full 7in text
width only resnet and lenet do. To clear 6pt in a column a figure must come in at
**≤399 units**, and the narrowest today is 750.

**These numbers moved when CASCADE left**, and the direction is the wrong one:
at 646 units it was the narrowest figure in the repository, so removing it took
the floor up to `resnet` at 750 and the best 7in result down from 7.4pt to 6.4pt.
The licence reason for removing it stands on its own; this is the cost. Flagged by
`draughtsman-d8` reading the gallery, and it is the third time the queue would
have gone stale about work done in the same day.

The correction-5 half: naming every axis at `14cfa91` made **six of eleven**
figures wider and none narrower, +50 to +55 units each, and no test noticed.
Every gain in honesty is paid for in width, the budget is never stated, and
nothing fails when it is overspent. `layout.wrap` is the right lever with no
target to solve against.

Nothing asserts the width of a committed figure. `tests/test_layout_shape.py`
passes `wrap=400` into synthetic layouts and reads as though it covers this; it
never touches the committed SVGs. A stranger finds out by putting one in a paper.

Shape of a fix, unbuilt: the spec states an output width and a minimum type size;
layout solves for it — wrap harder, drop detail lines, shrink the graph, **never
the type**; `check` fails when the effective point size falls under the floor. One
quantity, one implementation, something that fails. `render.py` and `layout.py`,
so `draughtsman-f0`'s if it is live, otherwise open.

**4. The PyPI name — done, with one optional remainder.** The distribution is
`draughtsman-nn` as of `0e2fa58`; the import package, the `draughtsman` command
and this repository keep the spelling. `tests/test_dist_name.py` ties the places
that state the name to `pyproject.toml`, the only executed one. The live defect
it exposed: `cli.py` told a reader without torch to pip-install the old
distribution name with a `trace` extra — not a stale promise but a working
instruction that fetches Kyle Fuller's API Blueprint parser. The exact string is
in `6814704`; it is deliberately not repeated here, because the guard in
`tests/test_dist_name.py` greps every tracked file for it and this file is not
exempt. Writing the defect down turned `main` red, which is the check working.

Open, and optional: asking Kyle Fuller for the name. They are active (GitHub
profile updated 2026-06-04) and `apiaryio/drafter`, the parser theirs wraps, is
archived — so the upstream that gave it its purpose is gone, which is the
argument to make. Owner consent is routine where a PEP 541 dispute over a package
that shipped releases usually fails. Not a blocker: nothing waits on it.

**Do not "simplify" this to `draftsman`.** The distribution name is free and the
import name is not: `factorio-draftsman` installs a top-level `draftsman/` and
released 2026-06-13. It trades a collision with a package abandoned in 2020 for
one with a package that ships. Checked by pulling the wheel.

**5. Email Peter Rupprecht about CASCADE.** *Tony's. The licence question is now
moot here; the email is worth sending anyway.*

CASCADE has left this repository — `examples/gallery/cascade*` removed, and the
model placed in `haruspex`, which is private and is itself a CASCADE
reimplementation, so GPL-3 never engages. That was the fallback and it is done, so
nothing is blocked on a reply.

What remains is an offer rather than an ask: two renderings of his network (34,381
parameters, 14 substantive operations, a 64-frame ΔF/F window in, one spike rate
out, every number read from the trace rather than typed) and the question of
whether either is useful for the repo or the docs. Worth telling him that every
pretrained CASCADE model is the same architecture and they differ only in training
set, resampling rate and target smoothing — a figure's caption makes a claim about
scope, and that one is easy to get wrong. If he is happy for the transcription to
sit under BSD-3 with attribution, the model can come back; if he never replies,
nothing changes. Tony has corresponded with him and reports him friendly and
prompt. Check whether he goes by Peter or Petr before sending.

**Do not rewrite history for this.** A public repo publishes its history, so the
file remains in `171210d` — and excising it would rewrite every hash after that
commit, which this file, `DECISIONS.md`, the site's claim ledger and the handoff
all cite. Re-deriving from Rupprecht et al. 2022 instead is a real option,
deliberately deferred: verify the paper carries the layer sizes first, since
`cascade.py` named `config.py` as the authority for them.

**6. Public-readiness, remainder.** Install instructions, the zero-dependency
claim, a friendly no-torch error and the supported-Python range are done — the
last of those at `787b1d4`, where `tests/test_versions.py` ties the README, the
`pyproject` floor and the CI matrix together. Not done: no `CONTRIBUTING` or issue
template for a repo that may be read as a record of working with Claude Code.

**8. Why some icons wrap and some do not is written down only on the mount.**
*Raised by Tony 2026-09-05; not decided.* `--icon` renders both layout candidates
and keeps whichever fills the slot larger, so an icon routinely does not match its
figure, and three different mechanisms produce that. `mlp` and `lstm` set no
`layout.wrap`, so the automatic width-budget fold fires. `lenet` and `resnet` set
one and the icon **overrules** it, because their committed form is taller than
wide. `vae`, `unet` and `whisper` state no `output.width`, so `width_budget`
returns `None`, the fold never fires, and both candidates come out byte-identical
— nothing is chosen, and the CLI still reports "as committed layout" as though
something had been.

So **"as committed layout" does not mean "wrapped"**, which is the part that
misleads. None of this is in the repository; it is in a README on the Dropbox
mount, which is the same failure this file's rule 1 is about. `DECISIONS.md` is
where it belongs. Two sessions independently reached that conclusion and neither
moved it without Tony.

**9. Two fills inside a box are still literal white.** `ds-lane` (lane label
plates) and `ds-meter-track` are `fill:#ffffff;fill-opacity:0.62`, at
`render.py:987` and `render.py:1039` as of `7e83e9b`. Every *stage* fill became
`var(--ds-fill-<kind>, <hex>)` so a mark can sit on a dark card; these two did
not, because they sit on a box fill rather than on the page and the file's ink
doctrine pins them there. That doctrine is right only while the box fill is light.

**No icon is affected** — both carry text and do not survive the text removal, at
420x104 or 192x96. A full figure embedded on a dark page is. Whoever takes this
should decide whether the doctrine wants a third case, not just patch the two.

**10. The darkroom now duplicates the ten committed icons, and it went stale.**
Item 7 above is out of date: `<darkroom>/draughtsman/` exists, and now holds
`icons-1x2/` — the same ten marks the repository commits as `examples/**/icon.svg`,
plus a contact sheet and the legibility findings, which the repo does not have.

The duplication is the problem. Those copies went stale within a day of being
made, twice: once when `tube`'s `layout.wrap` moved, once when stage fills became
restatable. Both times a person caught it. Either delete the copies and point at
the repo, keeping only the sheet and the write-up, or add a check — but two
uncoordinated copies of a generated artifact is the arrangement that just failed.

**7. Darkroom has no `draughtsman/` folder.** Every figure lives in git and in a
published artifact; none is in the estate's figure store, whose own README says a
figure nobody can re-run, date or attribute is one the next session re-derives.
`bugarach/net-figure-options/` — the regression suite `SPEC.md` §2 says to keep —
is also absent from it.
