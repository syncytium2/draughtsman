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
Six collisions exist right now. A test that simply forbade them would be red on
arrival, and a red test on `main` is one the next session learns to skip past. So
this pins the inventory exactly and allows movement in one direction only:
a figure may lose a collision or make one shallower, never gain one or make one
deeper.

That is deliberately not the same as "this is fine". Two of these are full
traversals and they are defects awaiting the router change, which is claimed
separately because it re-renders all ten figures. When that lands, the entries it
fixes come out of this table and the remaining ones get tighter. **Do not add a
row here to make a red run green** -- a new collision means the layout put an
edge through a box, and the fix is the layout, not the table.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from conftest import EXAMPLES, IDS, ROOT

sys.path.insert(0, str(ROOT / "tools"))

from edge_collisions import collisions            # noqa: E402

TOOL = ROOT / "tools" / "edge_collisions.py"

#: figure -> {(from, to, box): percent of the box crossed}, measured 2026-09-04
#: against `main` at 1c8fb40. A figure absent from this table must be clean.
BASELINE: dict[str, dict[tuple[str, str, str], float]] = {
    "dual": {("slow", "concat", "fast"): 100.0},
    "transformer": {("pos", "join1", "attn"): 42.0,
                    ("join1", "join2", "ff"): 26.0},
    "vae": {("noise", "sample", "sigma"): 79.0},
    "whisper": {("audio", "drest", "dcross"): 10.0},
    "tube": {("mean", "concat", "dog"): 76.0},
}

TOLERANCE = 1.0          # percentage points; re-rendering moves numbers slightly


@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_no_figure_gains_or_deepens_an_edge_through_a_box(d):
    """One direction only: collisions may go away, never arrive."""
    got = {(f, t, b): pct
           for f, t, b, _, _, pct in collisions((d / "figure.svg").read_text())}
    want = BASELINE.get(d.name, {})

    new = [k for k in got if k not in want]
    assert not new, (
        f"{d.name} has an edge running through a box that did not before: "
        + "; ".join(f"{f} -> {t} through {b!r} at {got[(f, t, b)]:.0f}%"
                    for f, t, b in new)
        + ". The layout put it there. Fix the routing, do not add it to BASELINE.")

    deeper = [(k, got[k], want[k]) for k in got
              if k in want and got[k] > want[k] + TOLERANCE]
    assert not deeper, (
        f"{d.name} has a collision that got worse: "
        + "; ".join(f"{f} -> {t} through {b!r} {was:.0f}% -> {now:.0f}%"
                    for (f, t, b), now, was in deeper))


def test_the_baseline_does_not_outlive_what_it_records():
    """A STALE BASELINE IS THE FAILURE MODE THIS REPOSITORY IS ABOUT.

    If a collision is fixed and its row stays, the table goes on asserting a
    defect that no longer exists and the next reader takes it for a to-do list.
    So an entry that no longer reproduces is a failure too -- in the direction of
    good news, with instructions.
    """
    stale = []
    for d in EXAMPLES:
        got = {(f, t, b) for f, t, b, _, _, _ in
               collisions((d / "figure.svg").read_text())}
        for key in BASELINE.get(d.name, {}):
            if key not in got:
                stale.append((d.name, key))
    assert not stale, (
        "these collisions are fixed and their BASELINE rows should be deleted: "
        + "; ".join(f"{n}: {f} -> {t} through {b!r}" for n, (f, t, b) in stale))


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
