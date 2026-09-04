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
Nine crossings exist right now. A test that simply forbade them would be red on
arrival, and a red test on `main` is one the next session learns to skip past. So
this pins the inventory exactly and allows movement in one direction only:
a figure may lose a crossing or make one shallower, never gain one or make one
deeper.

That is deliberately not the same as "this is fine". Nine crossings, four kinds:
`dual` is one unbroken traversal and is the defect awaiting the router change;
`vae` is a dashed edge riding a border it has no business touching; `whisper`
cuts one corner. The other six are three bypass arcs, each clipping two corners
of the stage it skips, and they want clearance rather than a route. When any of that lands, the entries it fixes come out of this
table and the rest get tighter. **Do not add a row here to make a red run green**
-- a new crossing means the layout put an edge through a box, and the fix is the
layout, not the table.

THE COUNT WENT FROM SIX TO NINE WITHOUT A FIGURE CHANGING, which is worth saying
plainly: the detector used to sum an edge's separate meetings with one box into a
single row. Nothing got worse. Three rows became six, three more stayed as they
were, and the sums that had been standing in for them were retired. See the BASELINE
comment for what the split showed.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from conftest import EXAMPLES, IDS, ROOT

sys.path.insert(0, str(ROOT / "tools"))

from edge_collisions import collisions            # noqa: E402

TOOL = ROOT / "tools" / "edge_collisions.py"

#: figure -> {(from, to, box, nth): percent of the box crossed}, re-measured
#: 2026-09-04 after the detector began reporting each contiguous crossing on its
#: own row. A figure absent from this table must be clean.
#:
#: THE KEY CARRIES `nth` BECAUSE THE OLD ONE COULD NOT HOLD THESE ROWS. Keyed on
#: (from, to, box) alone, an edge meeting a box twice has one slot, and the two
#: numbers collapse back into the single summed figure this change exists to undo.
#:
#: WHAT THE SPLIT REVEALED, AND IT IS THE REASON TO READ THIS TABLE AGAIN.
#: The six rows were never six of a kind:
#:
#:   dual        100%, ONE run          an edge straight through `fast`, in one
#:                                      side and out the other. The defect this
#:                                      tool was built for, and still the only
#:                                      one of its kind in the gallery.
#:   vae          79%, ONE run          the dashed noise edge rides up the right
#:                                      border of `sigma`, which it has nothing
#:                                      to do with. Real, and a clearance fault
#:                                      rather than a routing one.
#:   transformer  21% + 21%, 13% + 13%  a residual arc dipping under the stage it
#:   tube         38% + 38%             skips, clipping the near corner going down
#:                                      and the far corner coming up. `tube`
#:                                      labels its arc `bypass` in the figure.
#:   whisper      10%, ONE run          a single corner cut.
#:
#: The pairs are symmetric to the unit -- 26/26, 27/27, 70/70 -- because an arc
#: that bows under a box is symmetric about it. That symmetry is the signature of
#: a bypass, and summing the halves is what hid it: `tube` read 76% and
#: `transformer` 42%, both close enough to `dual`'s 100% to look like the same
#: fault, and neither one was.
BASELINE: dict[str, dict[tuple[str, str, str, int], float]] = {
    "dual": {("slow", "concat", "fast", 1): 100.0},
    "transformer": {("pos", "join1", "attn", 1): 21.0,
                    ("pos", "join1", "attn", 2): 21.0,
                    ("join1", "join2", "ff", 1): 13.0,
                    ("join1", "join2", "ff", 2): 13.0},
    "vae": {("noise", "sample", "sigma", 1): 79.0},
    "whisper": {("audio", "drest", "dcross", 1): 10.0},
    "tube": {("mean", "concat", "dog", 1): 38.0,
             ("mean", "concat", "dog", 2): 38.0},
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
