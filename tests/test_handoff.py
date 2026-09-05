"""A handoff expires, and its numbers are generated rather than typed.

Both rules were argued for in this repository before they were checked, which is
the state the board itself calls decoration.

WHY ONE. A handoff addresses exactly one reader: the next session. Once that
session has folded the live items into the queue it is history, and git already
holds history. Three were stacked in `CLAIMS.md` at once -- 2026-09-03 and 09-04 --
and nothing had ever expired one, so the oldest went on addressing "the first
session in this repo" long after that session was gone.

WHY GENERATED. Every measured quantity in those handoffs was produced once by a
tool in this repository and then pasted in by hand. A pasted number cannot go
stale loudly. It reads as a measurement forever, which is precisely the
confident-and-wrong figure this project convicts other tools of, arriving in the
document that makes the argument.

It is not hypothetical and it is not local. `armory/HANDOFF.md` states 306 tools
across 10 repositories while its own MANIFEST.json says 373 across 14, and the
superseded pair reached this repository: `.claude/hooks/dragnet-before-absence.py`
told every session that 34 of 306 tools are stranded off trunk, months after the
real figure moved.

So a handoff may carry a number only inside a block that names the command
producing it, and this re-runs that command.
"""

from __future__ import annotations

import re
import subprocess

from conftest import ROOT

BOARD = ROOT / "CLAIMS.md"

#: A generated block: a fence tagged `verified`, whose first line is the command
#: prefixed with `$ ` and whose remainder is that command's exact stdout.
BLOCK = re.compile(r"```verified\n\$ (?P<cmd>[^\n]+)\n(?P<out>.*?)```", re.S)


def test_at_most_one_handoff_is_live():
    """A superseded handoff is a to-do list nobody owns."""
    heads = re.findall(r"^\*\*0[a-z]\. HANDOFF\b.*$", BOARD.read_text(encoding="utf-8"),
                       re.M)
    assert len(heads) <= 1, (
        "more than one handoff is live on the board:\n  "
        + "\n  ".join(heads)
        + "\nA handoff has one reader. Fold the older one's live items into the "
          "queue and delete it -- git keeps the text.")


def test_every_number_a_handoff_states_still_reproduces():
    """The command is re-run and its output compared, so a stale figure is red.

    A block that drifts is the finding, not a nuisance: it means the sentence
    beside it has been describing a repository that no longer exists.
    """
    blocks = list(BLOCK.finditer(BOARD.read_text(encoding="utf-8")))
    assert blocks, (
        "no ```verified block on the board. A handoff that states no reproducible "
        "quantity is either carrying none, or carrying typed ones -- and typed is "
        "the thing this test exists to stop.")
    stale = []
    for m in blocks:
        cmd, want = m.group("cmd").strip(), m.group("out")
        got = subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True,
                             text=True).stdout
        if got.strip() != want.strip():
            stale.append(f"$ {cmd}\n  stated:\n{want.rstrip()}\n  now:\n{got.rstrip()}")
    assert not stale, (
        "a handoff states output its command no longer produces:\n\n"
        + "\n\n".join(stale)
        + "\n\nRe-run the command and paste the result, or delete the claim. "
          "Do not edit the number by hand -- that is how it got here.")
