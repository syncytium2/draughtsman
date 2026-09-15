"""`line` drawn beside `tube`, and the one property that makes it a comparison.

bugarach asked for the new architecture drawn BESIDE the old one rather than in
isolation, because what `line` changes is WHERE the ROI axis collapses — after
the bounded vote, not before the first kernel — and that is a difference between
two figures rather than a fact inside either. A reader can only see it if a mark
in one column is the size of a mark in the other.

So the assertions here are about the frame, not about the models: both panels
are held to one scale, the composite is held to its specs the way SPEC.md §6
holds every other committed figure, and `tools/beside.py`'s selftest is run and
then broken to prove it can fail. The figures themselves are covered by
`test_render.py` and `test_icon.py` like any other committed model —
`examples/line/` is one.

NOTHING HERE NEEDS TORCH. `examples/line/graph.json` is committed for the same
reason `examples/tube/graph.json` is: regenerating it needs bugarach, which this
repository does not depend on.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from conftest import ROOT
from draughtsman.check import check
from draughtsman.facts import Graph
from draughtsman.render import DETAIL_SIZE, render, type_pt
from draughtsman.spec import load

TOOL = ROOT / "tools" / "beside.py"
COMPOSITE = ROOT / "examples" / "line" / "beside-the-tube.svg"
PANELS = (ROOT / "examples" / "tube" / "beside-line.json",
          ROOT / "examples" / "line" / "beside-tube.json")

#: The floor every panel and the frame itself must clear, in points. The panels
#: declare it themselves as `output.min_type`; the frame has no spec to declare
#: it in, so it is stated once here and asserted against what was drawn.
TYPE_FLOOR = 6.0

_NESTED = re.compile(r'<svg x="[\d.]+" y="[\d.]+" width="([\d.]+)" '
                     r'height="([\d.]+)" viewBox="0 0 ([\d.]+) ([\d.]+)"')


def _spec_and_graph(path: Path):
    doc = json.loads(path.read_text())
    graph = Graph(json.loads(
        (path.parent / doc.get("graph", "graph.json")).read_text()))
    return load(doc), graph


@pytest.mark.parametrize("path", PANELS, ids=[p.parent.name for p in PANELS])
def test_each_panel_covers_its_graph(path):
    """A panel is a spec like any other and gets the same coverage rule. It is
    not held by `test_render.py`, which parametrises over `spec.json` alone."""
    spec, graph = _spec_and_graph(path)
    result = check(spec, graph)
    assert result.errors == []
    assert result.counts.exactly_once == result.counts.traced


def test_the_two_panels_agree_about_what_a_figure_unit_is_worth():
    """THE PROPERTY THE WHOLE FIGURE RESTS ON.

    Placed at 1:1 in one frame, two panels drawn for different output widths
    would put a 30-mark column beside a 30-mark column of a different size, and
    a reader comparing them would be comparing the page rather than the models.
    `beside.py` refuses such a pair; this is the committed pair being one.
    """
    worth = []
    for path in PANELS:
        spec, graph = _spec_and_graph(path)
        units = float(re.search(r'viewBox="0 0 ([\d.]+)',
                                render(spec, graph)).group(1))
        assert spec.output.width, f"{path.name} states no output.width"
        worth.append(type_pt(spec, units) / DETAIL_SIZE)
    assert worth[0] == pytest.approx(worth[1], abs=1e-9), (
        f"the panels are drawn at {worth[0]:.6f} and {worth[1]:.6f} points per "
        "figure unit. Beside each other that is two scales in one frame.")


def test_a_mark_means_the_same_thing_in_both_panels():
    """One scale is necessary and not sufficient: two columns of equal marks
    counting different axes would be worse than no comparison, because they
    would look like one. `check` already refuses two labellings inside ONE
    figure; nothing but this asks it across the pair."""
    labellings = set()
    for path in PANELS:
        spec, _ = _spec_and_graph(path)
        for stage in spec.stages:
            if stage.glyph:
                labellings.add((tuple(stage.glyph.labels), stage.glyph.style,
                                stage.glyph.scale))
    assert len(labellings) == 1, (
        "the panels glyph their axes differently, so the two mark columns do "
        f"not count the same thing: {sorted(labellings)}")


def test_the_committed_comparison_is_current():
    """SPEC.md §6 applied to a figure with two models in it. The panels are not
    committed — only this frame is — so re-running the tool is the only thing
    that can say the frame still matches the specs under it."""
    assert COMPOSITE.is_file(), f"{COMPOSITE} is missing"
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "beside.svg"
        r = subprocess.run([sys.executable, str(TOOL), *map(str, PANELS),
                            "-o", str(out)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        drawn = out.read_text()
    assert drawn == COMPOSITE.read_text(), (
        f"{COMPOSITE.name} is stale — re-run\n  python3 tools/beside.py "
        f"{PANELS[0].relative_to(ROOT)} {PANELS[1].relative_to(ROOT)} "
        f"-o {COMPOSITE.relative_to(ROOT)}\nand commit it.")


def test_the_panels_are_placed_and_not_scaled():
    """A nested `<svg>` whose width is not its viewBox extent is resampled, and
    a resampled panel is the one thing this figure must never contain."""
    nested = _NESTED.findall(COMPOSITE.read_text())
    assert len(nested) == 2, f"expected two nested panels, found {len(nested)}"
    for w, h, vw, vh in nested:
        assert (w, h) == (vw, vh), (
            f"a panel is drawn {w}x{h} for a {vw}x{vh} viewBox, so it is scaled")


def test_the_frame_is_legible_at_the_size_it_declares():
    """The panels each clear their own `output.min_type`; the frame around them
    has no spec to state one in, so it is asserted here instead of assumed. The
    frame's smallest type is the same DETAIL_SIZE the figures use."""
    svg = COMPOSITE.read_text()
    units = float(re.search(r'viewBox="0 0 ([\d.]+)', svg).group(1))
    inches = float(re.search(r'width="([\d.]+)in"', svg).group(1))
    got = DETAIL_SIZE * inches * 72.0 / units
    assert got >= TYPE_FLOOR, (
        f"the frame's smallest type is {got:.2f}pt at {inches:.2f}in, under the "
        f"{TYPE_FLOOR:g}pt floor.")


# --- the tool's own selftest, run and then broken ----------------------------
#
# tests/test_tools.py's standard: a selftest nothing invokes is the same defect
# one level out, and a selftest nothing has ever seen fail is decoration. Each
# mutation below removes one half of what the tool promises.

#: (what to break, what to replace it with, what the selftest must then say)
MUTATIONS = [
    ('f\'width="{p.w:.2f}" height="{p.h:.2f}" \'',
     'f\'width="{p.w / 2:.2f}" height="{p.h / 2:.2f}" \'',
     "is scaled"),
    ("if max(scales) - min(scales) > 1e-9:",
     "if False:",
     "different scales were composed"),
]


def test_beside_selftest_passes():
    r = subprocess.run([sys.executable, str(TOOL), "--selftest"],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, (
        "tools/beside.py --selftest failed:\n" + r.stdout + r.stderr)


@pytest.mark.parametrize("original,broken,says", MUTATIONS,
                         ids=["scales-a-panel", "accepts-two-scales"])
def test_beside_selftest_can_fail(original, broken, says):
    """THE ONLY VERSION OF THESE THAT MEANS ANYTHING.

    The tool is a composer, so every failure mode it has looks almost right:
    a panel quietly resampled, or a pair at two scales quietly accepted. Both
    would produce a file that opens and reads as a comparison. So each is put
    back and the selftest is required to go red on it by name.

    THE MUTANT RUNS FROM A TEMPORARY ROOT with `src` and `examples` linked back,
    because the tool resolves both against its own location and this must not
    write a broken copy into the repository to find out.
    """
    src = TOOL.read_text(encoding="utf-8")
    assert original in src, (
        f"the line this mutation breaks has moved:\n  {original}\nso it no "
        "longer reproduces the defect it guards, and is not guarding anything")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / "tools").mkdir()
        (tmp / "tools" / "broken.py").write_text(src.replace(original, broken, 1),
                                                 encoding="utf-8")
        for linked in ("src", "examples"):
            (tmp / linked).symlink_to(ROOT / linked, target_is_directory=True)
        r = subprocess.run([sys.executable, str(tmp / "tools" / "broken.py"),
                            "--selftest"], capture_output=True, text=True)
    assert r.returncode != 0, (
        f"with `{broken}` put back the selftest still passed, so it does not "
        "test what it claims to:\n" + r.stdout + r.stderr)
    assert says in r.stdout, (
        f"the selftest failed, but not on the {says!r} case:\n"
        + r.stdout + r.stderr)
