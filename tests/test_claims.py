"""CLAIMS.md is checked, or it is decoration.

DECISIONS.md correction 5: a quantity with one correct value that nothing verifies
goes wrong quietly. A claim board is exactly that shape -- it asserts who owns
which files, and the cost of it being stale is two sessions editing one function.
So the assertions it makes are checked here against the repository itself.

What this CANNOT check, and nobody should read a green run as covering: whether a
session is actually doing what its row says, and whether a session that never
wrote a row exists. Rule 5 in that file is a rule for people, not a test.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "CLAIMS.md"

# THE BOARD IS NEVER CLAIMED. Rule 2 says claim before you write, so if one
# session held CLAIMS.md every other session would have to edit a file it did not
# own in order to claim anything at all -- making the file that exists to prevent
# collisions the most contended file in the repository. Edits to it are one row
# and are expected to be concurrent. Found by draughtsman-f0.
UNCLAIMABLE = {"CLAIMS.md"}


def _rows() -> list[dict]:
    """The open-claims table, parsed. One dict per claim."""
    text = CLAIMS.read_text()
    body = text.split("## Open claims", 1)[1].split("## Queue", 1)[0]
    out = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 5 or cells[0] in ("session",):
            continue
        paths = [p.strip().strip("`") for p in cells[2].split(",") if p.strip()]
        out.append({"session": cells[0].strip("`"), "branch": cells[1].strip("`"),
                    "paths": paths, "since": cells[3], "doing": cells[4]})
    return out


def _touched(branch: str) -> list[str] | None:
    """What the branch has ACTUALLY changed against main.

    THE DECLARED PATHS ARE A HAND-MAINTAINED LIST, which is the failure mode this
    repository has spent two days on. This is the same list, computed, and the
    check below is that the hand-written one covers it.

    Returns None when the comparison cannot be made -- no such branch, no merge
    base -- so a missing branch is reported by its own assertion rather than
    twice.
    """
    out = subprocess.run(["git", "diff", "--name-only", f"origin/main...{branch}"],
                         cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        return None
    return [p for p in out.stdout.split() if p]


def _merged(branch: str) -> bool:
    out = subprocess.run(["git", "branch", "--all", "--merged", "origin/main"],
                         cwd=ROOT, capture_output=True, text=True)
    names = {n.strip().lstrip("* ").split("/")[-1] for n in out.stdout.splitlines()}
    return branch.split("/")[-1] in names


def _branches() -> set[str]:
    out = subprocess.run(["git", "for-each-ref", "--format=%(refname:short)",
                          "refs/heads", "refs/remotes"],
                         cwd=ROOT, capture_output=True, text=True, check=True)
    names = set()
    for ref in out.stdout.split():
        names.add(ref)
        if "/" in ref:
            names.add(ref.split("/", 1)[1])
    return names


def test_the_board_parses_and_every_row_is_well_formed():
    """AN EMPTY BOARD IS THE CORRECT BOARD when nobody is working, and in three
    months that is the expected state. An earlier version of this test required at
    least one row, which would have gone red forever the moment the last session
    released its claim -- a check firing on the right answer, in a repository whose
    argument is that its checks mean something."""
    assert CLAIMS.exists(), "CLAIMS.md is gone; the sessions have no shared record"
    for r in _rows():
        assert r["session"].startswith("draughtsman-"), r
        assert r["paths"], f"claim by {r['session']} names no paths"


def test_every_claim_names_a_branch_that_exists():
    """A claim on a branch nobody can find is a claim nobody can hand back."""
    known = _branches()
    missing = [(r["session"], r["branch"]) for r in _rows()
               if r["branch"] not in known]
    assert not missing, (
        f"claims name branches that do not exist: {missing}. Either the branch "
        "was deleted after landing and the row should have gone with it, or the "
        "row was written for work that never started.")


def test_every_claimed_path_exists():
    """A claim on a deleted file is stale, and a stale board is worse than none:
    it is read as current."""
    missing = [(r["session"], p) for r in _rows() for p in r["paths"]
               if not (ROOT / p).exists()]
    # A claim may legitimately name a file the claimant is about to create, so
    # this reports rather than fails when the branch itself is what is new.
    unexpected = [(s, p) for s, p in missing if not p.startswith("tests/")]
    assert not unexpected, f"claims point at paths that are not there: {unexpected}"


def test_no_two_open_claims_name_the_same_path():
    """THE ONE THIS FILE EXISTS FOR. Two sessions were both about to edit
    `render.py`'s `_box` today; it was caught by one of them asking, and nothing
    else would have caught it."""
    seen: dict[str, str] = {}
    clashes = []
    for r in _rows():
        for p in r["paths"]:
            if p in UNCLAIMABLE:
                continue
            if p in seen and seen[p] != r["session"]:
                clashes.append((p, seen[p], r["session"]))
            seen[p] = r["session"]
    assert not clashes, (
        "two sessions claim the same file: "
        + "; ".join(f"{p} claimed by {a} and {b}" for p, a, b in clashes))


def test_a_claim_covers_everything_its_branch_actually_touches():
    """THE ROW IS ONLY AS GOOD AS ITS PATHS, AND PATHS ARE TYPED BY HAND.

    draughtsman-e9 wrote a row naming three files and its branch touched nine.
    The two it left out included render.py, which another session was drawing in
    at the same time — so the board would have said both were clear while they
    were in one file. That is the failure the board exists to stop, arriving
    through an incomplete row rather than a missing one.

    A claim is still DECLARED, because a claim is made before the work exists and
    a computed list is empty then. What is checked is that the declaration has
    kept up with the branch: touch a file you did not claim and this fails.
    """
    escaped = []
    for r in _rows():
        touched = _touched(r["branch"])
        if touched is None:
            continue
        for path in touched:
            if path not in r["paths"]:
                escaped.append((r["session"], r["branch"], path))
    assert not escaped, (
        "branches have changed files their claim does not name:\n  "
        + "\n  ".join(f"{s} on {b} touched {p}" for s, b, p in escaped)
        + "\nAdd the path to the row, or stop editing the file. A row that has "
          "fallen behind its branch is worse than no row: it reads as current.")


def test_a_claim_whose_branch_has_landed_is_closed():
    """An open claim on merged work blocks somebody for no reason, and there is
    no way to tell from the row that it is spent."""
    spent = [(r["session"], r["branch"]) for r in _rows() if _merged(r["branch"])]
    assert not spent, (
        f"claims name branches already merged into main: {spent}. The work is "
        "done; remove the row so the file says what is actually open.")


def test_the_rule_the_board_cites_still_exists_under_that_number():
    """The board's whole argument is that it is correction 5 applied to the
    sessions rather than the figures. If that link rots the file becomes process
    for its own sake.

    THE FIRST VERSION OF THIS TEST DID NOT CHECK THE TARGET. It asserted that
    CLAIMS.md contained the string "correction 5" -- which CLAIMS.md controls --
    and that DECISIONS.md existed. Renumber the corrections and it would have
    stayed green while the citation pointed at nothing, which is precisely the
    failure it is named after. Found by draughtsman-f0.
    """
    board = CLAIMS.read_text()
    assert "correction 5" in board, "the board no longer cites its own rule"
    decisions = (ROOT / "DECISIONS.md").read_text()
    assert re.search(r"^### 5\. ", decisions, re.M), (
        "DECISIONS.md has no correction 5 under that number; CLAIMS.md cites it "
        "and the citation is now wrong. Renumbering a correction means fixing "
        "what points at it.")
