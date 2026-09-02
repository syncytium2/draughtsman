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


def test_the_board_parses_and_is_not_empty():
    """A board with no rows is a board nobody is using, and every session working
    this repository is supposed to have one."""
    assert CLAIMS.exists(), "CLAIMS.md is gone; the sessions have no shared record"
    rows = _rows()
    assert rows, "no open claims — either nobody is working, or nobody claimed"
    for r in rows:
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
            if p in seen and seen[p] != r["session"]:
                clashes.append((p, seen[p], r["session"]))
            seen[p] = r["session"]
    assert not clashes, (
        "two sessions claim the same file: "
        + "; ".join(f"{p} claimed by {a} and {b}" for p, a, b in clashes))


@pytest.mark.parametrize("doc", ["DECISIONS.md", "examples/gallery/README.md"])
def test_the_board_points_at_the_rule_it_applies(doc):
    """The board's whole argument is that it is correction 5 applied to the
    sessions themselves. If that link rots the file becomes process for its own
    sake, which is the thing it is trying not to be."""
    assert (ROOT / doc).exists()
    assert "correction 5" in CLAIMS.read_text(), (
        "CLAIMS.md no longer cites the rule it claims to be an instance of")
