"""SPEC.md §6 — generate, commit, verify.

The committed figure must be exactly what the committed spec and graph produce.
A model change that would move the figure then turns CI red instead of shipping a
picture of a model that no longer exists.

THIS TEST NEEDS NEITHER TORCH NOR GRAPHVIZ, which is the whole reason stage 3 is
ours rather than a system binary's. SPEC.md §8.2 worried that the staleness test
would drag graphviz into CI, in an estate where "a skip is what silence looks like
when it is being careful". There is nothing here to skip.
"""

import json
import re

import pytest

from conftest import EXAMPLES, IDS
from draughtsman.facts import Graph
from draughtsman.render import render
from draughtsman.spec import load
from draughtsman.text import width


@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_committed_figure_is_current(d):
    """Every committed model, not just the first. A spec edited without
    regenerating its figure is a repo shipping a picture of something else."""
    spec = load(json.loads((d / "spec.json").read_text()))
    graph = Graph(json.loads((d / "graph.json").read_text()))
    assert render(spec, graph) == (d / "figure.svg").read_text(), (
        f"{d}/figure.svg is stale — re-run "
        f"`draughtsman render {d}/spec.json -o {d}/figure.svg` and commit it."
    )


@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_every_committed_model_covers_its_graph(d):
    """The gallery is a regression sheet; this is the half of it a machine can
    check. Nine models passing by eye on the day they were made is not a
    property that stays true."""
    from draughtsman.check import check
    spec = load(json.loads((d / "spec.json").read_text()))
    result = check(spec, Graph(json.loads((d / "graph.json").read_text())))
    assert result.errors == []
    assert result.counts.exactly_once == result.counts.traced


def test_render_is_byte_stable_across_runs(tube_spec, tube_graph):
    assert render(tube_spec, tube_graph) == render(tube_spec, tube_graph)


def test_figure_carries_no_stylesheet_and_no_script(example_dir):
    """SPEC.md §4: ship no styling, inherit from the embedding page."""
    svg = (example_dir / "figure.svg").read_text()
    assert "<style" not in svg
    assert "<script" not in svg
    assert "@import" not in svg


def test_fills_are_inline_style_not_presentation_attributes(example_dir):
    """A `fill="…"` loses to any host rule. `.arch rect { fill: … }` in the
    embedding page repainted every glyph one flat colour the first time this was
    tried, so every fill here has to outrank that."""
    svg = (example_dir / "figure.svg").read_text()
    assert ' fill="' not in svg
    assert "style=\"fill:" in svg


def test_the_figure_says_what_the_reader_needs(example_dir):
    """SPEC.md §9: the fan-out to four kernels, the bypass, and the concat.
    All five tools in §2 failed this."""
    svg = (example_dir / "figure.svg").read_text()
    assert svg.count("ds-lane") == 4          # four kernels, drawn as four lanes
    # The bypass is distinguished by its LABEL, and deliberately not by dashing.
    # bugarach's eab8e59 replaced a diagram that "drew the bypass as a dashed
    # afterthought": it is a first-class fifth channel into the concat, and dashed
    # reads as optional. Asserting it is solid is the point, not an omission.
    assert "ds-edge-dashed" not in svg
    assert ">bypass<" in svg
    assert "concatenate" in svg


def test_ink_on_the_page_inherits_and_ink_on_a_box_does_not(example_dir):
    """SPEC.md §4 says inherit from the embedding page. Half-implementing that —
    pinning dark ink onto a ground the page owns — makes the title, the caption
    and every edge invisible on a dark page, which is what a README rendered in
    GitHub's dark theme is.

    So the split is by what a thing sits on. On a box fill this file chose:
    pinned. On the page: `currentColor`, still inline so a host rule cannot
    repaint it, and still black when the file stands alone.
    """
    svg = (example_dir / "figure.svg").read_text()

    def style_of(pattern):
        m = re.search(pattern, svg)
        assert m, f"no element matched {pattern}"
        return m.group(0)

    assert "currentColor" in style_of(r'<text class="ds-title"[^>]*>')
    assert "currentColor" in style_of(r'<text class="ds-caption"[^>]*>')
    assert "currentColor" in style_of(r'<path class="ds-edge[^>]*>')
    assert "currentColor" in style_of(r'<marker[^>]*>.*?</marker>')

    # a stage's own label sits on a fill this file chose, so it stays pinned
    box_label = re.search(r'<g class="ds-stage[^>]*>.*?(<text[^>]*>)', svg)
    assert box_label and "currentColor" not in box_label.group(1)

    # The legend sits below the body on the page's ground, so its text follows
    # the page and its SWATCHES do not — a swatch is the stated colour it is
    # there to identify, and inheriting would make the key illegible in the one
    # place it must not be.
    if "ds-legend" in svg:
        assert "currentColor" in style_of(r'<text class="ds-legend-label"[^>]*>')
        assert "currentColor" in style_of(r'<text class="ds-legend-share"[^>]*>')
        swatch = style_of(r'<rect class="ds-legend-swatch[^>]*>')
        assert "currentColor" not in swatch


def test_a_standalone_figure_still_has_ink(example_dir):
    """`currentColor` with no host resolves to black, so a file opened directly
    or rasterised for the PNG export looks exactly as it did before."""
    svg = (example_dir / "figure.svg").read_text()
    assert "<style" not in svg          # nothing is setting `color` for itself
    assert 'style="color' not in svg    # ... including on the root
# ---------------------------------------------------------------------------------
# HUE IS THE FAMILY. Tony's stated reason for wanting an Inception-style figure was
# "how much of the model is convolution, at a glance", and the first palette could
# not answer it: the DoG bank was gold and the dilated stack green, so the two
# convolutional stages of a 99%-convolution model read as unrelated.
# ---------------------------------------------------------------------------------

def test_the_convolutional_kinds_share_a_hue():
    from draughtsman.render import FAMILIES, PALETTE
    conv = [k for k, (fam, _) in FAMILIES.items() if fam == "conv"]
    assert {"kernel", "conv", "stack"} <= set(conv)
    # same hue, different value — so they group by colour and still separate in
    # a greyscale print, which is SPEC.md §4's constraint on this palette
    fills = {k: PALETTE[k][0] for k in conv}
    assert len(set(fills.values())) == len(conv), "values must differ"
    for hexcode in fills.values():
        r, g, b = (int(hexcode[i:i + 2], 16) for i in (1, 3, 5))
        assert g > r and g > b, f"{hexcode} is not in the green family"


def test_the_legend_is_generated_from_what_was_drawn(tube_spec, tube_graph):
    """A kind cannot appear in the drawing without appearing in the key —
    bugarach's own generator states that rule about its KINDS dict, and it is
    the right rule."""
    from draughtsman.render import _legend
    rows = _legend(tube_spec, tube_graph)
    drawn = {r[1] for r in rows}
    from draughtsman.render import FAMILIES
    expected = {FAMILIES.get(s.kind, FAMILIES["op"])[1] for s in tube_spec.stages}
    assert drawn == expected


def test_the_legend_share_is_counted_off_the_graph(tube_spec, tube_graph):
    """The number beside a swatch answers 'how much', so it has to be a fact.
    Every op and every parameter lands in exactly one legend row."""
    from draughtsman.render import _legend
    rows = _legend(tube_spec, tube_graph)
    ops = sum(int(r[2].split()[0]) for r in rows)
    params = sum(int(r[2].split(",")[1].strip().split()[0])
                 for r in rows if "params" in r[2])
    assert ops == len(tube_graph.traced)
    assert params == tube_graph.model["params"]


def test_convolution_is_most_of_the_tube(tube_spec, tube_graph):
    """The question the legend exists to answer, asserted on the model that
    prompted it."""
    from draughtsman.render import _legend
    conv = [r for r in _legend(tube_spec, tube_graph) if r[1] == "Convolution"]
    assert len(conv) == 1
    assert "1140 params" in conv[0][2]


def test_the_legend_is_off_unless_the_spec_asks(tube_spec, tube_graph):
    """Adding this field changed no committed figure but tube's."""
    import copy
    from draughtsman.render import render
    # Stripped of glyphs on both sides: a glyph carries its own legend row
    # whatever the flag says, because an unexplained rectangle is worse than a
    # legend nobody asked for. The flag governs the colour families, and that is
    # what this test is about.
    bare = copy.deepcopy(tube_spec)
    for st in bare.stages:
        st.glyph = None
    off = copy.deepcopy(bare)
    off.layout.legend = False
    bare.layout.legend = True
    assert "ds-legend" not in render(off, tube_graph)
    assert "ds-legend" in render(bare, tube_graph)


def test_a_glyph_carries_its_key_even_with_the_legend_off(tube_spec, tube_graph):
    """`tube` draws marks and sets no legend flag. The key still appears, and it
    has to: "one mark = one channel, a bar means more than 32" is the difference
    between a countable drawing and a decorative one."""
    import copy
    from draughtsman.render import render
    off = copy.deepcopy(tube_spec)
    off.layout.legend = False
    assert any(st.glyph for st in off.stages), "tube lost its glyphs"
    assert "one mark = one" in render(off, tube_graph)


def test_meters_scale_against_the_largest_in_their_series(tube_spec_doc,
                                                          tube_graph):
    """FULL BAR IS THE SERIES MAXIMUM AND EMPTY IS ZERO. A stage holding most of
    the model's parameters should read as a nearly full bar, because it does.
    The legend has to state what full means, or the bar is a number with no unit.
    """
    import copy
    from draughtsman.spec import load
    doc = copy.deepcopy(tube_spec_doc)
    for stage in doc["stages"]:
        if stage["id"] in ("dog", "head"):
            stage["meters"] = [{"value": "{stage.params}", "label": "params"}]
    svg = render(load(doc), tube_graph)

    assert "ds-meter-track" in svg and "ds-meter-fill" in svg
    assert "full bar =" in svg, "the legend must carry the meter's scale"

    fills = [float(m) for m in re.findall(
        r'class="ds-meter-fill"[^>]*?width="([\d.]+)"', svg)]
    tracks = [float(m) for m in re.findall(
        r'class="ds-meter-track"[^>]*?width="([\d.]+)"', svg)]
    assert len(fills) == len(tracks) == 2
    # ONE LENGTH FOR EVERY TRACK IN THE FIGURE. If tracks stretched to fit their
    # boxes, equal values would draw unequal bars and the reader would be
    # comparing box widths instead of the quantity.
    assert len(set(tracks)) == 1, "tracks must not depend on their box's width"
    # The series maximum fills its track exactly; nothing overflows.
    assert any(abs(f - tracks[0]) < 0.01 for f in fills)
    assert all(f <= tracks[0] + 0.01 for f in fills)


def test_a_spec_without_meters_renders_exactly_as_before(tube_spec, tube_graph):
    """The feature must be inert when unused, which is what keeps every
    committed figure byte-identical across its introduction."""
    assert "ds-meter" not in render(tube_spec, tube_graph)


def _glyphed(doc, ids, **over):
    """`axes` indexes the shape AS DRAWN, so it follows the spec's batch_axis.

    tube declares `batch_axis: 0`, so the drawn shape is (channels, frames) and
    the glyph's axes are 0 and 1. Before the batch axis could be hidden these
    read [1, 2]; a spec carrying two axis numberings — one for its labels and
    one for its glyphs — is DECISIONS.md correction 5 in miniature, so there is
    exactly one, and it is the numbering the reader sees.
    """
    import copy
    d = copy.deepcopy(doc)
    # `tube` now carries glyphs of its own, and these tests use its spec as a
    # blank canvas. A test that builds a scenario on a committed spec has to
    # neutralise what it does not control, or it fails the day the corpus gains
    # a feature -- which is what happened here. Stripped from the COPY: the first
    # version of this stripped `doc`, which is the session-scoped fixture, and
    # would have corrupted every test that ran after it.
    for s in d["stages"]:
        s.pop("glyph", None)
    drop = 1 if d.get("batch_axis") is not None else 0
    for stage in d["stages"]:
        if stage["id"] in ids:
            stage["glyph"] = {"of": "{stage.out_shape}",
                              "axes": [1 - drop, 2 - drop],
                              "labels": ["channels", "frames"], **over}
    return d


def test_the_glyph_scales_both_edges_and_never_resizes_the_box(tube_spec_doc,
                                                               tube_graph):
    """THE ENCODING IS THE GLYPH, NOT THE BOX. A box is sized by its text and is
    an input to the layout engine, so an encoding put there would be clamped by
    the longest label — a truncated baseline, silently."""
    from draughtsman.spec import load
    from draughtsman.render import GLYPH_H, GLYPH_W

    # Both sides from the same glyph-free baseline. `tube` draws MARKS, which
    # widen a box on purpose — that is the one glyph style whose size is its
    # claim — so comparing against the committed spec would be comparing marks
    # with blocks and calling it a regression.
    import copy
    bare = copy.deepcopy(tube_spec_doc)
    for st in bare["stages"]:
        st.pop("glyph", None)
    plain = render(load(bare), tube_graph)
    doc = _glyphed(bare, {"dog", "head", "concat"}, scale="linear")
    svg = render(load(doc), tube_graph)

    boxes = lambda s: re.findall(r'<rect x="([\d.]+)" y="[\d.]+" '
                                r'width="([\d.]+)"', s)
    assert [b[1] for b in boxes(plain)] == [b[1] for b in boxes(svg)], \
        "adding a glyph must not change any box's width"

    g = [(float(w), float(h)) for w, h in re.findall(
        r'class="ds-glyph"[^>]*?width="([\d.]+)" height="([\d.]+)"', svg)]
    assert len(g) == 3
    # The figure's largest value in each axis fills that edge of the canvas.
    assert max(w for w, _ in g) == GLYPH_W
    assert max(h for _, h in g) == GLYPH_H
    assert all(w <= GLYPH_W + 0.01 and h <= GLYPH_H + 0.01 for w, h in g)
    assert "each edge scales with value" in svg, "the legend must name the scale"


def test_sqrt_is_the_default_and_compresses_less_faithfully_but_visibly(
        tube_spec_doc, tube_graph):
    """Channel counts in this gallery span 1568:1. A linear edge there puts the
    smallest rectangle under a pixel, so the default compresses — and says so."""
    from draughtsman.spec import load
    lin = render(load(_glyphed(tube_spec_doc, {"dog", "head"}, scale="linear")),
                 tube_graph)
    sq = render(load(_glyphed(tube_spec_doc, {"dog", "head"})), tube_graph)
    # SPELLED OUT, NOT ∝ AND √. Those two codepoints are not carried by
    # Liberation Sans or by many Arial builds, so the sentence that explains the
    # compression rendered as boxes on the machines least likely to have
    # Helvetica. What is asserted is unchanged: the legend must say WHICH scale.
    assert "each edge scales with the square root of value" in sq
    assert "each edge scales with value" in lin

    # tube's extent is 600 at every stage, so width is constant and carries
    # nothing here — which is itself the honest reading. Height is the axis that
    # varies, so that is the one the compression can be measured on.
    small = lambda s: min(float(h) for h in re.findall(
        r'class="ds-glyph"[^>]*?height="([\d.]+)"', s))
    assert small(sq) > small(lin), "sqrt must lift the smallest edge, not lower it"


def test_a_caption_does_not_set_the_figure_s_width(tube_graph, tube_spec_doc):
    """A 416-character caption made U-Net 1831px wide — the figure sized by a
    sentence rather than by the drawing — and clipped its own last word anyway,
    because fitting exactly leaves no margin for a text metric to be wrong in.
    Prose wraps to the drawing; the drawing does not stretch to the prose."""
    import copy
    short = copy.deepcopy(tube_spec_doc)
    short["caption"] = "Short."
    long = copy.deepcopy(tube_spec_doc)
    long["caption"] = "word " * 300

    def w(doc):
        svg = render(load(doc), tube_graph)
        return float(re.search(r'viewBox="0 0 ([\d.]+) ', svg)[1])

    assert w(long) == w(short)


def test_a_long_caption_wraps_and_keeps_every_word(tube_graph, tube_spec_doc):
    import copy
    doc = copy.deepcopy(tube_spec_doc)
    doc["caption"] = " ".join(f"word{i}" for i in range(120))
    svg = render(load(doc), tube_graph)
    lines = re.findall(r'class="ds-caption"[^>]*>([^<]*)<', svg)
    assert len(lines) > 1
    assert " ".join(lines) == doc["caption"], "wrapping lost or reordered words"


def test_every_caption_line_fits_inside_the_figure(tube_graph, tube_spec_doc):
    """The bug was a line running past the canvas edge, so this measures the
    lines rather than trusting that wrapping happened."""
    import copy
    from draughtsman.render import CAPTION_SIZE
    from draughtsman.text import width as text_width
    doc = copy.deepcopy(tube_spec_doc)
    doc["caption"] = " ".join(f"word{i}" for i in range(120))
    svg = render(load(doc), tube_graph)
    total = float(re.search(r'viewBox="0 0 ([\d.]+) ', svg)[1])
    for line in re.findall(r'class="ds-caption"[^>]*>([^<]*)<', svg):
        assert 12 + text_width(line, CAPTION_SIZE) <= total - 12 + 0.01, line


@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_no_committed_caption_overflows(d):
    """All eleven, against the committed files rather than a constructed case."""
    from draughtsman.render import CAPTION_SIZE
    from draughtsman.text import width as text_width
    svg = (d / "figure.svg").read_text()
    total = float(re.search(r'viewBox="0 0 ([\d.]+) ', svg)[1])
    for line in re.findall(r'class="ds-caption"[^>]*>([^<]*)<', svg):
        assert 12 + text_width(line, CAPTION_SIZE) <= total - 12 + 0.01, (
            f"{d.name}: caption line runs past the canvas — {line!r}")


# --- text on line art -------------------------------------------------------
#
# interface2 ships `tools/pdf_overlap_check.py` for this class and states its own
# blind spot in the docstring: it compares text against TEXT, so "a label sitting
# on a trace with NO background box would be invisible to this tool." That is
# exactly the defect this file asserts against — a stage name painted over the
# sheets it names, which is what `layout.chrome: "none"` produced on every LeNet
# stage whose stack reached the title line.
#
# The tool is in `armory` as `origin/interface2/tools/pdf_overlap_check.py`,
# status `stranded` — committed there, never merged anywhere. It reads PDFs, so
# it could not have run on an SVG even if it had travelled. Here the geometry is
# generated rather than measured, so the assertion is cheap and exact.

_TITLE_RE = re.compile(
    r'<text x="([-\d.]+)" y="([-\d.]+)" text-anchor="middle" '
    r'style="[^"]*font-size:12\.0px;font-weight:600[^"]*">([^<]*)</text>')
_SHEET_RECT_RE = re.compile(
    r'<rect class="ds-sheet" x="([-\d.]+)" y="([-\d.]+)" '
    r'width="([\d.]+)" height="([\d.]+)"')
_SHEET_POLY_RE = re.compile(r'<polygon class="ds-sheet" points="([^"]+)"')

TITLE_SIZE_PX = 12.0


def _ink_boxes(group: str):
    """Every piece of glyph ink in one stage, as (x0, y0, x1, y1)."""
    out = []
    for x, y, w, h in _SHEET_RECT_RE.findall(group):
        x, y, w, h = float(x), float(y), float(w), float(h)
        out.append((x, y, x + w, y + h))
    for pts in _SHEET_POLY_RE.findall(group):
        xs, ys = [], []
        for pair in pts.split():
            px, py = pair.split(",")
            xs.append(float(px))
            ys.append(float(py))
        out.append((min(xs), min(ys), max(xs), max(ys)))
    return out


@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_no_stage_name_is_painted_over_its_own_glyph(d):
    """A name on top of the drawing it names is never intentional."""
    svg = (d / "figure.svg").read_text()
    hits = []
    checked = 0
    for group in re.findall(r'<g class="ds-stage.*?</g>', svg, re.S):
        ink = _ink_boxes(group)
        if not ink:
            continue
        m = _TITLE_RE.search(group)
        if not m:
            continue
        checked += 1
        cx, base, text = float(m.group(1)), float(m.group(2)), m.group(3)
        w = width(text, TITLE_SIZE_PX, bold=True)
        # A text baseline sits under the glyphs; the cap height is what can
        # collide, and a descender below the baseline is not part of a title.
        t = (cx - w / 2.0, base - TITLE_SIZE_PX * 0.72, cx + w / 2.0, base)
        for b in ink:
            if t[0] < b[2] and b[0] < t[2] and t[1] < b[3] and b[1] < t[3]:
                hits.append((d.name, text))
                break
    # THE GUARD, and it is not decoration. `tests/test_edge_labels.py` found its
    # stage footprints by parsing ink that stopped being drawn, so it quietly
    # had nothing to check; it caught that only because it asserted it had
    # parsed something. A figure with no glyphs legitimately checks nothing, so
    # the guard is on the SUITE rather than on each figure.
    assert checked or 'class="ds-sheet"' not in svg, (
        f"{d.name}: the figure draws sheets but this parsed no titled stage "
        "with ink, so the comparison below had nothing to make and would pass "
        "vacuously")
    assert not hits, (
        "stage names are painted over their own glyph ink: "
        + ", ".join(f"{fig}:{name!r}" for fig, name in hits)
        + ". Text on line art is the collision class that is never intentional, "
          "and it is the one interface2's overlap checker states it cannot see."
    )


# --- sheet geometry ---------------------------------------------------------

@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_equal_axis_values_draw_equal_lengths(d):
    """THE ASPECT A READER SEES MUST BE THE TENSOR'S, NOT THE CANVAS'S.

    Each axis once had its own canvas and its own maximum, so a 64×64 map — the
    same number twice — drew 44 wide and 28 tall and every square tensor in the
    gallery came out at 1.45:1. One span fixed it; this is what keeps it fixed.

    Checked on the drawn SVG rather than on the constants, because the constants
    agreeing proves nothing about what was rendered.
    """
    spec_raw = json.loads((d / "spec.json").read_text())
    sheets = [s for s in spec_raw["stages"]
              if (s.get("glyph") or {}).get("style") == "sheets"]
    svg = (d / "figure.svg").read_text()
    nodes = {n["id"]: n
             for n in json.loads((d / "graph.json").read_text())["nodes"]}

    bad, checked = [], 0
    for st in sheets:
        shaped = [n for n in st["nodes"]
                  if n in nodes and nodes[n].get("out_shape")]
        if not shaped:
            continue
        shape = nodes[shaped[-1]]["out_shape"]
        if len(shape) != 4 or shape[2] != shape[3]:
            continue                      # only square maps prove the point
        group = re.search(
            r'<g class="ds-stage[^>]*data-stage="%s".*?</g>' % re.escape(st["id"]),
            svg, re.S)
        if not group:
            continue
        m = re.search(r'<rect class="ds-sheet" x="[-\d.]+" y="[-\d.]+" '
                      r'width="([\d.]+)" height="([\d.]+)"', group.group(0))
        if not m:
            continue
        w, h = float(m.group(1)), float(m.group(2))
        checked += 1
        if abs(w - h) > 0.05:
            bad.append((st["id"], shape[2], shape[3], w, h))
    # The guard, for the reason `test_edge_labels` needed one: a figure that
    # stopped drawing what this parses would make the assertion vacuous rather
    # than red.
    # NOT A SKIP. `DRAUGHTSMAN_NO_SKIPS` fails the run when a test goes quiet —
    # "give the test what it needs, or delete it" — and a figure with no sheet
    # glyphs genuinely has nothing to check rather than something it cannot
    # reach. So it passes, and the guard below only binds where sheets exist.
    assert checked or not sheets, (
        f"{d.name}: has sheet glyphs but no square map was measured, so this "
        "assertion had nothing to compare")
    assert not bad, (
        "square spatial maps are not drawn square: "
        + ", ".join(f"{sid} is {a}×{b} drawn {w:.2f}×{h:.2f}"
                    for sid, a, b, w, h in bad)
        + ". Equal axis values must draw equal lengths, or the aspect the reader "
          "sees belongs to the canvas rather than to the tensor."
    )


# --- two type sizes ---------------------------------------------------------

_FONT_SIZE_RE = re.compile(r"font-size:([\d.]+)px")


@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_a_figure_uses_two_type_sizes(d):
    """Eight sizes is noise. Two is hierarchy, and one of them is the floor.

    There were eight — 14, 12, 10, 9.5, 9, 9, 9, 8 and 7 — none of them chosen as
    a set. Each arrived with a feature that wanted to be slightly smaller than the
    last. Hierarchy in a figure that will be reduced onto a journal column has to
    come from weight, position and colour, because half a point of size does not
    survive the reduction.

    AND IT IS WHAT MAKES THE PAGE BUDGET HONEST. `width_budget` derives the
    output scale from the smallest type in the figure. While there were eight
    sizes that number was DETAIL_SIZE by assumption and 7.0 in fact, so a figure
    could pass the legibility check carrying type under the floor it had just
    promised to hold. With two, the smallest is knowable by construction.
    """
    sizes = sorted({float(v) for v in
                    _FONT_SIZE_RE.findall((d / "figure.svg").read_text())})
    assert sizes, f"{d.name}: parsed no type sizes at all"
    assert len(sizes) <= 2, (
        f"{d.name} draws {len(sizes)} type sizes: {sizes}. A figure gets a head "
        "size and a body size. Anything that wants a third is asking for weight "
        "or colour instead.")


def test_the_page_budget_uses_the_smallest_type_there_is():
    """The floor must be computed from the smallest size the renderer emits."""
    from draughtsman import render as R
    emitted = {R.TITLE_SIZE, R.DETAIL_SIZE, R.LANE_SIZE, R.CAPTION_SIZE,
               R.LEGEND_SIZE, R.EDGE_LABEL_SIZE, R.METER_SIZE}
    assert min(emitted) == R.DETAIL_SIZE, (
        f"the smallest type the renderer emits is {min(emitted)}, but "
        f"width_budget scales the page from DETAIL_SIZE ({R.DETAIL_SIZE}). The "
        "legibility floor would be computed against type that is not the "
        "smallest, so a figure could pass while printing under its own floor."
    )


# ---------------------------------------------------------------- legend width
#
# THE FIGURE IS AS WIDE AS ITS DRAWING, NOT AS WIDE AS ITS PROSE. render.py has
# argued this once already, in the comment excluding the caption from the width
# max: "a 416-character caption made U-Net 1831px wide -- the figure's width set
# by a sentence rather than by the drawing". The legend's share text was still a
# term in that same max one line below, and it cost `lenet` 103 units: the glyph
# note `deepest = 16, tallest = 28, widest = 28 · each edge ∝ √value` reached 792
# units against a drawing that reached 719.
#
# `layout.wrap` could not reach it. Every value from 760 down to 280 left the
# width at 822.19 to the hundredth and only made the figure taller, because the
# wrap solver arranges boxes and this was a sentence. A reader of that sweep would
# conclude the figure was irreducible.

def _viewbox_w(svg: str) -> float:
    return float(re.search(r'viewBox="0 0 ([\d.]+)', svg).group(1))


def test_lenet_is_as_wide_as_its_drawing_and_not_as_wide_as_its_legend():
    """THE REGRESSION, NAMED BY ITS NUMBER, AND IT IS NARROWER THAN IT LOOKS.

    lenet shipped at 822.19 units while its drawing reached 719: the glyph note
    `deepest = 16, tallest = 28, widest = 28 · each edge ∝ √value · ...` ran to
    792 and the figure grew to hold it on one line. `layout.wrap` could not touch
    it -- 760 down to 280 all left the width at 822.19 to the hundredth and only
    added height, because the wrap solver arranges boxes and this was a sentence.

    TWO ATTEMPTS AT A GENERAL INVARIANT FAILED, AND BOTH PASSED ON THE DEFECT,
    which is worth more than this assertion is:

      1. Monkeypatching `_legend` to pad every share. Fired on 1 figure of 10,
         and not on lenet. The glyph note is not one of `_legend`'s rows -- it is
         built inside `render` from the glyph axes and appended to them.
      2. Re-rendering with `layout.legend: false` and comparing widths. Fired on
         0 of 10, on the shipped code, because that flag gates `_legend`'s rows
         and the appended glyph row is emitted regardless of it.

    So the rule -- prose wraps to the drawing, the drawing does not stretch to
    the prose -- is stated in `render.py` and guarded here only by the one case
    that broke, plus the containment check below. A general form needs the glyph
    note to come from the same seam as the rest of the legend, which is a change
    to `render.py` and not to this file.
    """
    d = next(p for p in EXAMPLES if p.name == "lenet")
    svg = (d / "figure.svg").read_text()
    total = _viewbox_w(svg)
    assert total < 500, (
        f"lenet is {total:.2f} units wide. It was 822.19 when its legend set its "
        "width; anything near that means the legend is back in the width max.")

    shares = [m for m in re.finditer(
        r'<text class="ds-legend-share"([^>]*)>(.*?)</text>', svg, re.S)]
    assert len(shares) > 1, (
        "lenet's legend share is on one line again, so either the note got short "
        "or it stopped wrapping -- and this test's premise is gone either way")


@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_no_legend_line_is_drawn_outside_the_figure(d):
    """Wrapping prose to the drawing is only half the rule; the other half is
    that it then FITS. The caption fix had to be made twice for exactly this --
    fitting exactly left 12px of margin for a text metric to be wrong in, and it
    was wrong by under one percent, and the last word was cut. So this measures
    the drawn result rather than trusting the wrap limit that produced it."""
    svg = (d / "figure.svg").read_text()
    total = _viewbox_w(svg)
    for m in re.finditer(r'<text class="ds-legend-share"([^>]*)>(.*?)</text>',
                         svg, re.S):
        attrs, body = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
        x = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))
        size = float(re.search(r"font-size:([\d.]+)px", attrs).group(1))
        right = x + width(body, size)
        assert right <= total, (
            f"{d.name}: a legend line reaches {right:.1f} in a {total:.1f}-unit "
            f"figure, so it is clipped: {body!r}")


# --------------------------------------------------------------------------------
# THE FIGURE'S METRICS AND THE READER'S.
#
# `text.py` computes advance widths from a table; the reader's font engine computes
# them again at display time; the figure is correct only while those agree. That is
# the last two-place quantity in this repository that nothing reconciles, and it is
# the one a reader actually sees. These three tests hold the two places together
# from the only side a test can reach without a rasteriser: what we emit, and what
# we admit we are guessing.


def test_the_font_stack_survives_the_attribute_it_is_written_into():
    """`Helvetica Neue` unquoted is not a valid CSS family name, and engines that
    reject it drop the WHOLE declaration rather than the one bad token — falling
    through to the platform default, which on Linux is DejaVu Sans and is wider
    than Helvetica at every size. That is how an outside reviewer rasterised this
    gallery and found the ResNet legend overrunning its own viewBox.

    The quotes must be SINGLE. `FONT_STACK` is interpolated into `style="..."` on
    every text element, so double quotes would close the attribute and produce a
    broken file — the fix for an unquoted font name being far worse than the
    defect. The XML parse below is what would catch that.
    """
    from draughtsman.text import FONT_STACK

    assert "'Helvetica Neue'" in FONT_STACK, (
        f"the multi-word family is unquoted in {FONT_STACK!r}; engines that "
        "reject it fall through to the platform default and the figure is then "
        "laid out to metrics it is not being drawn with")
    assert '"' not in FONT_STACK, (
        f"{FONT_STACK!r} carries a double quote, which closes the style "
        'attribute it is written into')


@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_every_committed_figure_is_well_formed_xml(d):
    """The cheap half of the check above, run against the artifact rather than the
    constant. A malformed attribute is invisible in a diff and total in a reader."""
    from xml.dom.minidom import parseString

    parseString((d / "figure.svg").read_text())


@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_no_figure_asks_for_a_glyph_the_pinned_stack_cannot_draw(d):
    """U+221D PROPORTIONAL TO and U+221A SQUARE ROOT are not carried by Liberation
    Sans or by many Arial builds, so the legend that explained the glyph scale
    rendered as two boxes on exactly the machines least likely to have Helvetica.

    `render.py` used to emit both, in `each edge ∝ √value`. It now spells the
    relation out. This is the assertion that keeps them from coming back, and it
    is about OUR text: the Greek in a spec is the author's word for their own
    model and is not ours to refuse.
    """
    svg = (d / "figure.svg").read_text()
    for ch, name in (("∝", "U+221D PROPORTIONAL TO"),
                     ("√", "U+221A SQUARE ROOT")):
        assert ch not in svg, (
            f"{d.name}/figure.svg contains {name}, which the pinned font stack "
            "does not reliably carry — it renders as a box. Spell the relation "
            "out in words instead.")


def test_which_glyphs_are_estimated_is_pinned_rather_than_silent():
    """`width()` CANNOT FAIL ON AN UNKNOWN GLYPH — it must return a number, so an
    unmeasured character is absorbed at `_DEFAULT` and nothing says so. That is a
    hand-maintained value with one correct answer going quiet, which is
    `DECISIONS.md` correction 5 arriving in the type case.

    So the gap is pinned instead of asserted away. These eleven characters have no
    advance width in `text.py` and are estimated; `×`, `—`, `–` and `·` were in
    this set until they were measured, and `×` alone appears 146 times across the
    gallery because every shape string carries one.

    A NEW estimated glyph fails this test. That is the point: adding one is a
    decision, and it should cost a line here rather than nothing.
    """
    import re as _re

    from draughtsman.text import unmeasured

    known = set("εμσ₁₂₃₄₅₆"
                "→⊙")
    found: set[str] = set()
    for d in EXAMPLES:
        svg = (d / "figure.svg").read_text()
        for m in _re.finditer(r">([^<]*)</text>", svg):
            found |= unmeasured(m.group(1))
    new = found - known
    assert not new, (
        "the gallery renders characters with no advance width in text.py, so "
        "their boxes are sized from a guess: "
        + " ".join(f"U+{ord(c):04X} {c!r}" for c in sorted(new))
        + ". Measure them into `_W`, or add them here and say why they are "
          "acceptable as estimates.")


# A FILL IS RESTATABLE, AND THE FALLBACK IS WHAT KEEPS TODAY'S FIGURES TODAY'S.
# tonydefazio.com could not put a mark on a dark card because the fills were
# literal hex for a light plate. They are now var(--ds-fill-<kind>, <hex>), so a
# host restates the ground and a standalone file does not move.

def test_every_stage_fill_is_restatable_and_falls_back_to_the_palette():
    from draughtsman.render import PALETTE, paint
    for kind, (fill, stroke) in PALETTE.items():
        f, s = paint(kind)
        assert f == f"var(--ds-fill-{kind},{fill})", kind
        assert s == f"var(--ds-stroke-{kind},{stroke})", kind
    # an unknown kind falls to "op" in BOTH the name and the value, so a host
    # restating --ds-fill-op catches it rather than it going unreachable
    assert paint("no-such-kind") == paint("op")


@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_no_stage_fill_is_emitted_as_bare_hex(d):
    """The fallback lives inside the var(), never beside it. A bare palette hex
    in the output is a fill some host can never restate."""
    from draughtsman.render import PALETTE
    svg = (d / "figure.svg").read_text()
    bare = {h for h, _ in PALETTE.values() if f"fill:{h}" in svg}
    assert not bare, f"{d}/figure.svg emits unrestatable fills: {sorted(bare)}"


# --- chrome per stage ---------------------------------------------------------
#
# THE SIGNATURE CHANGE OWES WHAT THE MULTI-INPUT CHANGE PAID. `--input-shape`
# became repeatable and one shape still produced byte-identical output, so
# nothing traced before it meant anything different. `chrome` is now a field of a
# stage as well as of a figure, and the equivalent claim is below: a figure that
# says it once renders exactly as a figure that says it on every stage, and a
# spec that says nothing per stage renders exactly as it did.
#
# `test_committed_figure_is_current` above is the other half, and the wider one:
# it re-renders all ten committed specs -- two of which set `layout.chrome` --
# and requires byte-identity with the committed file.

@pytest.mark.parametrize("d", EXAMPLES, ids=IDS)
def test_saying_chrome_per_stage_is_the_same_as_saying_it_once(d):
    doc = json.loads((d / "spec.json").read_text())
    graph = Graph(json.loads((d / "graph.json").read_text()))
    figure_level = render(load(doc), graph)

    moved = json.loads(json.dumps(doc))
    chrome = (moved.get("layout") or {}).get("chrome", "box")
    if "layout" in moved:
        moved["layout"].pop("chrome", None)
    for stage in moved["stages"]:
        # A stage that already answers for itself keeps its answer -- what is
        # being tested is that the FIGURE's answer means the same thing said
        # per stage, not that a per-stage answer can be overwritten.
        stage.setdefault("chrome", chrome)
    assert render(load(moved), graph) == figure_level, (
        f"{d.name}: moving layout.chrome onto every stage changed the figure. "
        "The per-stage path is meant to be the same path, so an existing spec "
        "cannot mean anything different after this change.")


def test_a_stage_can_keep_its_box_while_the_others_lose_theirs(tube_spec, tube_graph):
    """WHAT THE FIELD IS FOR, and the case that forced it.

    `tube` draws marks and its last stage is a per-frame score, which is words.
    Figure-level chrome could box all seven or bare all seven; the rule the page
    runs on wants six bare and one boxed.
    """
    doc = json.loads(json.dumps(_as_doc(tube_spec)))
    for stage in doc["stages"]:
        stage["chrome"] = "none" if stage.get("glyph") else "box"
    svg = render(load(doc), tube_graph)
    for stage in doc["stages"]:
        m = re.search(r'<g class="ds-stage[^"]*" data-stage="%s"[^>]*>(.*?)</g>'
                      % stage["id"], svg, re.S)
        assert m, f"{stage['id']} is not in the figure"
        drew_a_rect = "<rect" in m.group(1)
        if stage.get("glyph"):
            assert not drew_a_rect or 'data-box=' in m.group(0), (
                f"{stage['id']} asked for no chrome and drew a stage rect")
        else:
            assert drew_a_rect, f"{stage['id']} asked for a box and drew none"


def test_a_bare_stage_still_publishes_its_extent(tube_spec, tube_graph):
    """The collision checker reads `data-box` where there is no rect to find.

    A stage that goes bare inside a boxed figure is the new way to become
    invisible to it, which is DECISIONS.md correction 11 -- a guard that loses
    its subject reports all clear -- arriving through a new door.
    """
    doc = json.loads(json.dumps(_as_doc(tube_spec)))
    bare = [s for s in doc["stages"] if s.get("glyph")][0]
    bare["chrome"] = "none"
    svg = render(load(doc), tube_graph)
    m = re.search(r'<g class="ds-stage[^"]*" data-stage="%s"([^>]*)>' % bare["id"], svg)
    assert m and "data-box=" in m.group(1), (
        f"{bare['id']} went bare and published no extent, so the edge-collision "
        "checker cannot see it and will report the figure clean.")


def test_a_stage_chrome_typo_is_refused(tube_spec):
    doc = _as_doc(tube_spec)
    doc["stages"][0]["chrome"] = "non"
    with pytest.raises(ValueError, match="chrome must be"):
        load(doc)


def _as_doc(spec):
    from draughtsman.spec import dump
    return dump(spec)
