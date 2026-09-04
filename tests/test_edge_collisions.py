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

WHY THIS WAS A BASELINE AND NOT A FLOOR, AND WHY IT NOW AMOUNTS TO ONE.
No figure has an edge through a box. The table below is empty, so this test now
fails on any crossing at all -- which is what it always wanted to do and could not
while six existed. A test that forbade them on arrival would have been red from
the start, and a red test on `main` is one the next session learns to skip past;
pinning the inventory and allowing movement in one direction only is what got the
inventory to zero without ever shipping a red suite.

**Do not add a row to make a red run green.** A new crossing means the layout put
an edge through a box, and the fix is the layout, not the table.

THE COUNT WENT SIX -> NINE -> ONE -> ZERO. Splitting an edge's separate meetings
with a box into their own rows added no defect and removed none; it stopped three
bypasses from reading as near-traversals and made the remaining work legible.
Giving a bypass room took eight away. Putting the wrap connector in its own gutter
took the last one, which was never a bypass at all.
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

#: figure -> {(from, to, box, nth): percent of the box crossed}. EMPTY, and that
#: is the whole point of having kept it.
#:
#: It was six, across five figures. Splitting an edge's separate meetings with a
#: box into their own rows made it nine and showed the six were never six of a
#: kind: `dual` was one unbroken traversal, `vae` a dashed edge riding a border,
#: `whisper` one corner cut, and the other six rows were three bypass arcs, each
#: clipping the near corner of the stage it skips going down and the far corner
#: coming up -- symmetric to the unit, 26/26, 27/27, 70/70, because a bow under a
#: box is symmetric about it. Summing the halves had hidden exactly that.
#:
#: Two changes emptied it, and they were different faults with different fixes.
#: Giving a bypass the WIDTH of the rank it crosses made it run level beneath the
#: stage instead of dipping to a point, which cleared eight. Putting the wrap
#: connector's return lane in the GUTTER already reserved for it -- rather than at
#: the midpoint between its two endpoints, a number about two boxes and not about
#: the rows they sit on -- cleared the ninth. No figure changed size for either.
#:
#: KEEP THE TABLE AND KEEP IT EMPTY. An empty baseline makes this a floor in
#: effect: any crossing at all is now a failure, which is what the check always
#: wanted to be and could not be while six existed. A row added here is a
#: deliberate, argued decision to tolerate a figure claiming a path the model does
#: not contain -- not a way to green a red run.
BASELINE: dict[str, dict[tuple[str, str, str, int], float]] = {}

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


#: An edge from `a` to `b` straight through `c`. Deliberately synthetic -- see
#: `test_the_detector_can_fail` for why this is not one of the gallery figures.
_CROSSES = """<svg viewBox="0 0 200 100">
<g class="ds-stage ds-kind-op" data-stage="a"><rect x="10" y="10" width="40" height="30"/></g>
<g class="ds-stage ds-kind-op" data-stage="b"><rect x="150" y="10" width="40" height="30"/></g>
<g class="ds-stage ds-kind-op" data-stage="c"><rect x="80" y="10" width="40" height="30"/></g>
<path class="ds-edge ds-edge-solid" data-from="a" data-to="b" d="M50 25 L150 25"/>
</svg>"""


def test_the_detector_can_fail():
    """THE ONLY VERSION OF THE TEST ABOVE THAT MEANS ANYTHING, and the mutation
    is the bug this tool actually shipped with for an hour.

    The Liang-Barsky clipper had its (p, q) pairs the wrong way round, which
    makes `t0` land past `t1` on every real crossing, so the segment is discarded
    and the tool reports a figure with an edge straight through a box as clean.
    A checker that cannot fail in the direction it exists for is worse than none.

    IT USED TO RUN AGAINST `dual`, AND FIXING `dual` DISARMED IT. The guard needed
    a figure with a crossing in it, and the gallery had one, so it used it. When
    the wrap connector was moved into its own gutter and `dual` came out clean,
    this test could no longer tell the mutated clipper from the real one and
    failed -- correctly, and for a reason that had nothing to do with the clipper.

    A guard against a detector going blind must not depend on the thing it detects
    still being present in the work. The fixture is synthetic now, so emptying the
    baseline cannot quietly take the mutation guard with it.
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
    assert ns["collisions"](_CROSSES) == [], (
        "the mutation did not actually break the clipper, so this test proves "
        "nothing about the real one")
    hit = collisions(_CROSSES)
    assert hit and hit[0].box == "c" and hit[0].pct > 95, (
        "the real clipper no longer reports an edge drawn straight through a box, "
        "which is the mutation's behaviour, not the fixed one's")
