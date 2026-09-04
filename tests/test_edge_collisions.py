"""No edge may run through a box it has nothing to do with.

An arrow drawn through a stage is a figure making a claim the model does not: a
reader of `dual` sees the wide branch's output pass through the narrow branch on
its way to the concatenate, and there is no such path in the trace. That is the
confident-and-wrong figure this repository convicts other tools of, in its own
gallery.

IT PASSED EVERYTHING. Coverage green, the legibility gate green, the byte-exact
render test green. `tests/test_edge_labels.py` checks that an edge's LABEL does
not sit on a box; nothing had ever asked where the edge's own path goes. Found on
2026-09-04 by Tony looking at a rendering and saying there was something in it he
did not think the session could see -- correctly, because that session was
measuring type size, unit width and print points, and none of those asks whether
the drawing reads as a drawing.

WHY THIS IS A BASELINE AND NOT A FLOOR, WHICH IS THE UNCOMFORTABLE PART.
One crossing exists right now, and this still pins rather than forbids. A floor
set at zero goes red the moment anything regresses, with no record of what was
tolerated or why, and a red test on `main` is one the next session learns to skip
past. Movement is allowed in one direction only: a figure may lose a crossing or
make one shallower, never gain one or make one deeper. **Do not add a row here to
make a red run green** -- a new crossing means the layout put an edge through a
box, and the fix is the layout, not the table.

That is deliberately not the same as "this is fine". `dual` is a figure claiming a
path the trace does not contain, it is on a figure the project page publishes, and
it is the last one left.

IT IS NOT A BYPASS, which is why the change that cleared the other eight did not
touch it. `slow` and `concat` sit on rows the layout wrapped, so the edge takes the
wrap route: out to the right margin, down, back along a RETURN LANE, and in. The
lane's height is the midpoint between the source's bottom and the target's top --
and nothing asks whether a stage is standing there. In `dual` one is: the lane sits
at y=175.0 and `fast` spans y=112.5..183.0, so the run back to the left margin
crosses it end to end. That is the 100%, and the fix is how the lane is chosen, not
how a skip is drawn.

THE COUNT WENT SIX -> NINE -> ONE, and only the last step changed a figure.
Splitting an edge's separate meetings with a box into their own rows added no
defect and removed none; it stopped three bypasses from reading as near-traversals
and made the shape of the remaining work legible. Giving a bypass room then took
eight rows away at once. See the BASELINE comment for what the split showed.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from conftest import EXAMPLES, IDS, ROOT

sys.path.insert(0, str(ROOT / "tools"))

from edge_collisions import collisions            # noqa: E402

TOOL = ROOT / "tools" / "edge_collisions.py"

#: figure -> {(from, to, box, nth): percent of the box crossed}. One row now, and
#: how it got to one is worth more than the row.
#:
#: It was six, across five figures. Splitting an edge's separate meetings with a
#: box into their own rows made it nine and showed the six were never six of a
#: kind: `dual` was one unbroken traversal, `vae` a dashed edge riding a border,
#: `whisper` one corner cut, and the other six rows were three bypass arcs, each
#: clipping the near corner of the stage it skips going down and the far corner
#: coming up. The pairs were symmetric to the unit -- 26/26, 27/27, 70/70 --
#: because an arc bowing under a box is symmetric about it, and summing the halves
#: had hidden exactly that signature.
#:
#: Giving a bypass the WIDTH of the rank it crosses, so it runs flat beneath the
#: stage instead of dipping to a point at its centre, cleared eight of the nine and
#: re-routed three more skips that had never registered. No figure changed size.
#: What is left was never a bypass.
BASELINE: dict[str, dict[tuple[str, str, str, int], float]] = {
    "dual": {("slow", "concat", "fast", 1): 100.0},
}

TOLERANCE = 1.0          # percentage points; re-rendering moves numbers slightly


@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_no_figure_gains_or_deepens_an_edge_through_a_box(d):
    """One direction only: collisions may go away, never arrive."""
    got = {(c.frm, c.to, c.box, c.nth): c.pct
           for c in collisions((d / "figure.svg").read_text())}
    want = BASELINE.get(d.name, {})

    new = [k for k in got if k not in want]
    assert not new, (
        f"{d.name} has an edge running through a box that did not before: "
        + "; ".join(f"{f} -> {t} through {b!r} (crossing {n}) at {got[k]:.0f}%"
                    for k in new for f, t, b, n in [k])
        + ". The layout put it there. Fix the routing, do not add it to BASELINE."
        " A crossing that gained an `nth` is an edge that now meets that box an"
        " extra time, which is the same finding as a new row.")

    deeper = [(k, got[k], want[k]) for k in got
              if k in want and got[k] > want[k] + TOLERANCE]
    assert not deeper, (
        f"{d.name} has a collision that got worse: "
        + "; ".join(f"{f} -> {t} through {b!r} (crossing {n}) {was:.0f}% -> {now:.0f}%"
                    for (f, t, b, n), now, was in deeper))


def test_the_baseline_does_not_outlive_what_it_records():
    """A STALE BASELINE IS THE FAILURE MODE THIS REPOSITORY IS ABOUT.

    If a collision is fixed and its row stays, the table goes on asserting a
    defect that no longer exists and the next reader takes it for a to-do list.
    So an entry that no longer reproduces is a failure too -- in the direction of
    good news, with instructions.
    """
    stale = []
    for d in EXAMPLES:
        got = {(c.frm, c.to, c.box, c.nth)
               for c in collisions((d / "figure.svg").read_text())}
        for key in BASELINE.get(d.name, {}):
            if key not in got:
                stale.append((d.name, key))
    assert not stale, (
        "these collisions are fixed and their BASELINE rows should be deleted: "
        + "; ".join(f"{name}: {f} -> {t} through {b!r} (crossing {n})"
                    for name, (f, t, b, n) in stale))


def test_the_detector_selftest_passes():
    r = subprocess.run([sys.executable, str(TOOL), "--selftest"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_detector_can_fail():
    """THE ONLY VERSION OF THE TEST ABOVE THAT MEANS ANYTHING, and the mutation
    is the bug this tool actually shipped with for an hour.

    The Liang-Barsky clipper had its (p, q) pairs the wrong way round, which
    makes `t0` land past `t1` on every real crossing, so the segment is discarded
    and the tool reports a figure with an edge straight through a box as clean.
    A checker that cannot fail in the direction it exists for is worse than none.
    """
    src = TOOL.read_text(encoding="utf-8")
    good = "for p_, q_ in ((-dx, x1 - rx1), (dx, rx2 - x1),\n" \
           "                   (-dy, y1 - ry1), (dy, ry2 - y1)):"
    assert good in src, (
        "the clipper has been rewritten; this mutation no longer reproduces the "
        "defect it guards, so it is not guarding anything")
    broken = src.replace(good,
                         "for p_, q_ in ((dx, x1 - rx1), (-dx, rx2 - x1),\n"
                         "                   (dy, y1 - ry1), (-dy, ry2 - y1)):", 1)
    ns: dict = {}
    exec(compile(broken, "edge_collisions_mutated", "exec"), ns)   # noqa: S102
    dual = next(p for p in EXAMPLES if p.name == "dual")
    assert ns["collisions"]((dual / "figure.svg").read_text()) == [], (
        "the mutation did not actually break the clipper, so this test proves "
        "nothing about the real one")
    assert collisions((dual / "figure.svg").read_text()), (
        "the real clipper now reports dual as clean, which is the mutation's "
        "behaviour, not the fixed one's")
