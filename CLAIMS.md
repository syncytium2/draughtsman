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

2. **Claim before you write, in the same commit that starts the work.**
   *Because:* two sessions were both about to edit `render.py`'s `_box`. It was
   caught by one of them asking. Nothing would have caught it otherwise.

3. **A claim names paths, not intentions.** "the layout" is not a claim;
   `src/draughtsman/layout.py` is.
   *Because:* `check.py` was touched six times today and `test_coverage.py` five,
   by two sessions, and two of those collided as append-append conflicts in the
   same test file.

4. **Release a claim when the branch lands.** An open claim on merged work blocks
   somebody for no reason, and nothing in the row says it is spent. Checked.

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

6. **A session that does not appear here is not accounted for.** One session
   worked this repo for eighteen hours before the other two knew it existed. This
   is the one rule nothing can check.

## Open claims

| session | branch | paths | since | doing |
|---|---|---|---|---|
| `draughtsman-fa` | `claim-board` | `CLAIMS.md`, `tests/test_claims.py`, `README.md` | 2026-09-02 | This file and its check |

`draughtsman-f0` and `draughtsman-e9` hold no claims. `name-every-axis` landed as
`cb7fc2a` and its row was removed by the check that noticed it had.

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

**3. The glyph is still under consideration.** Tony has `block` and now `marks`
in front of him and has not settled. Nothing should be built on top of the glyph
until he does, and only CASCADE declares one, so the cost of a reversal is one
spec file.

**4. Meters and glyphs exist on one model out of eleven.** U-Net is the strongest
candidate — a glyph per stage would make it read as a U in channel space, which
`examples/gallery/README.md` notes a ranked layout cannot produce. Blocked on 3.

**5. Public-readiness, remainder.** Install instructions, the zero-dependency
claim and a friendly no-torch error are done. Not done: nothing states which
Python versions are supported outside CI, and no `CONTRIBUTING` or issue template
exists for a repo that may be read as a record of working with Claude Code.

**6. Darkroom has no `draughtsman/` folder.** Every figure lives in git and in a
published artifact; none is in the estate's figure store, whose own README says a
figure nobody can re-run, date or attribute is one the next session re-derives.
`bugarach/net-figure-options/` — the regression suite `SPEC.md` §2 says to keep —
is also absent from it.
