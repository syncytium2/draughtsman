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

2. **Claim before you write, and land the claim on `main` before the work.**
   A branch's `CLAIMS.md` is a copy nobody else can read.
   *Because:* two sessions were both about to edit `render.py`'s `_box`, caught
   only by one of them asking — and later, two sessions each claimed U-Net's
   glyphs on their own branch, could not see each other, and built the same figure
   twice. The check now compares against `origin/main:CLAIMS.md`, so a claim that
   has not landed protects nobody.

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
| `draughtsman-65` | `dist-name` | `pyproject.toml`, `src/draughtsman/cli.py`, `README.md`, `tests/test_dist_name.py`, `tests/test_ui.py` | 2026-09-02 | `pip install draughtsman` fetches someone else's package, and `cli.py` tells a reader to run it |

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

**3. NO FIGURE IS LEGIBLE AT A JOURNAL COLUMN WIDTH.** Measured by
`draughtsman-65` and reproduced independently. Detail text is 9.5 units; figures
are 646–1737 units wide, so placing one in a 3.5in column scales the type to
between 1.4pt and 3.7pt. **Nothing clears 6pt at 3.5in.** At the full 7in text
width only cascade, lenet and resnet do. To clear 6pt in a column a figure must
come in at **≤399 units**, and the narrowest today is 646.

The correction-5 half: naming every axis at `14cfa91` made **six of eleven**
figures wider and none narrower, +50 to +55 units each, and no test noticed.
Every gain in honesty is paid for in width, the budget is never stated, and
nothing fails when it is overspent. `layout.wrap` is the right lever with no
target to solve against.

Shape of a fix, unbuilt: the spec states an output width and a minimum type size;
layout solves for it — wrap harder, drop detail lines, shrink the graph, **never
the type**; `check` fails when the effective point size falls under the floor. One
quantity, one implementation, something that fails. `render.py` and `layout.py`,
so `draughtsman-f0`'s if it is live, otherwise open.

**4. `pip install draughtsman` INSTALLS SOMEONE ELSE'S PACKAGE.** PyPI
`draughtsman` is Kyle Fuller's API Blueprint parser, 0.2.0, last released
2020-03-26 — verified against the PyPI JSON API, not assumed. `pyproject.toml`
declares `name = "draughtsman"`, which cannot be uploaded. Needs a distribution
name that is free, or a PEP 541 name transfer, and transfers take weeks. **Start
before any publish, not after.** Found by `draughtsman-65`.

**5. Public-readiness, remainder.** Install instructions, the zero-dependency
claim, a friendly no-torch error and the supported-Python range are done — the
last of those at `787b1d4`, where `tests/test_versions.py` ties the README, the
`pyproject` floor and the CI matrix together. Not done: no `CONTRIBUTING` or issue
template for a repo that may be read as a record of working with Claude Code.

**6. Darkroom has no `draughtsman/` folder.** Every figure lives in git and in a
published artifact; none is in the estate's figure store, whose own README says a
figure nobody can re-run, date or attribute is one the next session re-derives.
`bugarach/net-figure-options/` — the regression suite `SPEC.md` §2 says to keep —
is also absent from it.
