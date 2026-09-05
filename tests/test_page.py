"""The page decision, as checks rather than as a request.

DECISIONS.md, "What the page leads with", is the decision: the page leads with
and predominantly shows the tensor drawn to scale -- `glyph` with `chrome: none`
-- and a box with text is the fallback, for stages whose content is genuinely
words.

WHY IT IS HERE AND NOT IN A PROMPT. Nothing in this repository stated which
representation the site led with, and the field defaults are a box and a block,
so every regeneration re-derived the page from the defaults and landed in the
same place. A decision nothing checks is a decision that reverts. This is the
executable half, and it is the same pattern the icon section already uses: CI
re-renders every committed mark and reads the slot back out of the file.

WHAT IS NOT CHECKED HERE, and it is recorded in DECISIONS.md rather than left to
be rediscovered: `chrome` is a figure-level field, so the per-stage rule cannot
yet be expressed and `tube` draws marks inside boxes -- named below as the one
exemption, so that anything new fails.

"Every boxed stage either has word content or carries a written reason" was
withdrawn (rev. 2) and is not attempted: a machine cannot tell whether a stage's
content is words, and the nearest proxy fires on 55 stages here, most of them
correctly boxed. A check that fires on 55 correct figures is one somebody turns
off, which is the reasoning the mark bands already run on. What replaces it is a
RATCHET rather than a gate -- see the baseline at the bottom of this file. It
makes no claim about which stages are right; it only refuses a silent rise, which
is the drift the decision was written against.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "index.html"

# `tube` draws `marks` glyphs inside boxes, and it stays that way ON EVIDENCE
# rather than for want of a way to say otherwise. `chrome` is a field of a stage
# now, so the figure can be written the other way in one line -- it was, and the
# contact sheet refused it. Bared, tube's mark keeps its four lane strips and one
# box and loses everything else: `--icon` strips the mark columns as sub-pixel
# detail, and with no boxes there is no bulk left to survive. The scale rises
# from 0.20x to 0.34x and the band calls that "reads", which is the band
# measuring the size of what is left rather than whether anything is.
#
# So the rule holds and this figure is the exception, with the measurement as its
# reason. DECISIONS.md, "What the page leads with", carries it.
GLYPH_IN_A_BOX_EXEMPT = {"tube"}


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def _figures() -> list[Path]:
    """Every committed figure the page shows, in the order it shows them.

    Marks are excluded: the icon grid is about what survives a shrink, not about
    how a figure represents a stage, and it draws every model by design.
    """
    out = []
    for src in re.findall(r'<img[^>]+src="(examples/[^"]+)"', _page()):
        if src.endswith("figure.svg") and (ROOT / src).exists():
            out.append(ROOT / src)
    return out


def _spec(figure: Path) -> dict:
    return json.loads((figure.parent / "spec.json").read_text(encoding="utf-8"))


def _glyph_stages(spec: dict) -> list[dict]:
    return [s for s in spec.get("stages", []) if s.get("glyph")]


def _is_bare(spec: dict) -> bool:
    return spec.get("layout", {}).get("chrome") == "none"


# --- what the page opens with ------------------------------------------------

def test_the_opening_pair_includes_a_figure_drawn_to_scale():
    """AMENDED FROM "the first figure", AND THE MEASUREMENT IS WHY.

    The decision asked for a scaled stage in the first figure and named
    `whisper`'s log-mel input as the candidate. It cannot be one: a glyph's claim
    is comparative -- each edge is scaled against the biggest value at that axis
    position anywhere in the figure -- so the only glyph in a figure draws at full
    canvas whatever its tensor is. A second glyph would restore the comparison and
    `check` refuses it, because Whisper's stages label their axes differently.

    So the banner keeps Whisper, which is the reason the multi-input and
    tied-weight work exists, and the demonstration sits directly under it. What is
    checked is the first SCREEN rather than the first figure.
    """
    figures = _figures()
    assert len(figures) >= 2, f"the page shows {len(figures)} figures"
    opening = figures[:2]
    scaled = [f for f in opening if _glyph_stages(_spec(f)) and _is_bare(_spec(f))]
    assert scaled, (
        "neither of the first two figures on the page draws a tensor to scale: "
        f"{[f.parent.name for f in opening]}. The page's own argument is that a "
        "box with numbers in it is what a tracer already gives you; a reader's "
        "first screen has to contain the thing only this tool asserts.")


def test_the_banner_carries_its_written_reason_for_having_no_glyph():
    """The exception lands in a diff, which is the rule this repository runs on."""
    spec = json.loads((ROOT / "examples/gallery/whisper/spec.json").read_text())
    notes = " ".join(s.get("note", "") for s in spec["stages"])
    assert "NO GLYPH" in notes, (
        "whisper/spec.json no longer says why the model this page leads with "
        "carries no tensor drawn to scale. Without it the next session re-derives "
        "the answer from the defaults, adds a lone glyph, and ships a decoration.")


# --- the rule, where it is decidable -----------------------------------------

def test_no_figure_on_the_page_draws_a_glyph_inside_a_box():
    offenders = [f.parent.name for f in _figures()
                 if _glyph_stages(_spec(f)) and not _is_bare(_spec(f))
                 and f.parent.name not in GLYPH_IN_A_BOX_EXEMPT]
    assert not offenders, (
        f"{offenders} draw a tensor inside a box. A rectangle around a rectangle "
        "gives the eye two things to read and it settles on the larger, which is "
        "the box -- so the drawing that carries the claim is the one that loses. "
        "Set layout.chrome to none, or take the glyph off.")


def test_the_exemption_is_still_a_real_one():
    """An allowlist nobody rechecks is a permanent hole with a comment on it."""
    stale = [name for name in GLYPH_IN_A_BOX_EXEMPT
             if not any(f.parent.name == name and _glyph_stages(_spec(f))
                        and not _is_bare(_spec(f)) for f in _figures())]
    assert not stale, (
        f"{stale} no longer draws a glyph inside a box, or is no longer on the "
        "page. Take it out of GLYPH_IN_A_BOX_EXEMPT so the rule covers it again.")


def test_every_glyph_figure_states_its_scale():
    """`sqrt` is a nonlinear mapping and an unstated one is a lie about area."""
    missing = []
    for f in _figures():
        spec = _spec(f)
        styles = {s["glyph"].get("style") for s in _glyph_stages(spec)}
        if not styles:
            continue
        svg = f.read_text(encoding="utf-8")
        if styles <= {"marks"}:
            ok = "one mark = one" in svg          # marks are counted, not scaled
        else:
            ok = "each edge scales with" in svg
        if not ok:
            missing.append(f"{f.parent.name} ({', '.join(sorted(styles))})")
    assert not missing, (
        f"{missing}: the figure draws tensors to scale and its key does not say "
        "how. Rooting each edge preserves order and changes area; a reader who is "
        "not told reads the area as the tensor.")


# --- page order ---------------------------------------------------------------

# The order the decision sets, by section id rather than by heading, so the prose
# can be rewritten without failing this.
ORDER = ["to-scale", "compare", "fields", "marks"]


def test_the_section_order_matches_the_decision():
    page = _page()
    seen = [m for m in re.findall(r'<section[^>]*\bid="([\w-]+)"', page) if m in ORDER]
    assert seen == ORDER, (
        f"the page's sections run {seen}; the decision sets {ORDER}. The "
        "demonstration goes above the field tour: at present the tensor drawn to "
        "scale would be described in prose while the nearest figure is boxed.")


def test_the_demonstration_comes_before_the_first_boxed_figure_of_our_own():
    """The concrete defect the decision was written against.

    The `lenet` figure -- the clearest instance of the tool's distinguishing claim
    -- sat below ten icon thumbnails, about three quarters of the way down, while
    the page led with boxes.
    """
    page = _page()
    first_scaled = min((page.index(f"examples/gallery/{f.parent.name}/figure.svg")
                        for f in _figures()
                        if _glyph_stages(_spec(f)) and _is_bare(_spec(f))), default=-1)
    assert first_scaled > 0, "the page shows no figure that draws a tensor to scale"
    assert first_scaled < page.index('id="marks"'), (
        "the first figure drawing a tensor to scale appears below the icon grid, "
        "which is where this decision found it.")


def test_the_glyph_and_chrome_blocks_show_what_they_describe():
    """REV. 2 DESCOPED THIS TO TWO BLOCKS, and named why.

    Adjacency only ever mattered for `glyph` and `chrome`, because those were the
    two describing a tensor drawn to scale while the nearest figure was boxed. The
    page leading with the scaled figure largely settles it; what is checked is that
    each of the two still points at the figure that shows it, so a later edit
    cannot quietly leave them describing something the reader cannot see.
    """
    page = _page()
    for field in ("glyph", "chrome"):
        m = re.search(r"<h3>[^<]*<code>" + field + r"</code></h3>(.*?)</div>",
                      page, re.S)
        assert m, f"the field tour no longer has a block for {field}"
        assert 'href="#to-scale"' in m.group(1), (
            f"the {field} block describes a tensor drawn to scale and points at "
            "nothing that shows one. The demonstration is on the same page.")


# --- the ratchet ---------------------------------------------------------------

# Boxed stages that print a shape, per model, as they stand. NOT a claim that any
# of these is wrong: most are right, and the judgement about which is not
# mechanisable, which is why the criterion that tried to gate it was withdrawn.
# It is a floor. A regeneration that re-derives a figure from the defaults adds
# boxes printing shapes, and nothing else here would notice.
#
# TO RAISE ONE OF THESE NUMBERS, RAISE IT DELIBERATELY, in the same commit as the
# spec that needs it and with the reason in the message. That is the whole
# mechanism: the number is cheap to change and impossible to change by accident.
BOXED_SHAPE_STAGES = {
    "dual": 6, "lenet": 5, "lstm": 5, "mlp": 5, "resnet": 2,
    "transformer": 10, "tube": 1, "vae": 10, "whisper": 11,
}


def _boxed_shape_stages() -> dict[str, int]:
    out = {}
    for spec_path in sorted(ROOT.glob("examples/*/spec.json")) + \
            sorted(ROOT.glob("examples/gallery/*/spec.json")):
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        n = sum(1 for s in spec.get("stages", [])
                if not s.get("glyph")
                and any("shape" in d for d in s.get("detail", [])))
        if n:
            out[spec_path.parent.name] = n
    return out


def test_no_model_grows_more_boxed_stages_that_print_a_shape():
    now = _boxed_shape_stages()
    risen = {k: (BOXED_SHAPE_STAGES.get(k, 0), v) for k, v in now.items()
             if v > BOXED_SHAPE_STAGES.get(k, 0)}
    assert not risen, (
        "more stages draw a box around a shape than the baseline allows: "
        + ", ".join(f"{k} {was} -> {is_}" for k, (was, is_) in sorted(risen.items()))
        + ".\nThe defaults are a box and a block, so this is what drift back to "
          "them looks like. If the new box is right, raise the number here in the "
          "same commit and say why.")


def test_the_baseline_has_not_gone_stale_downward():
    """A floor that has quietly risen above the ground stops being a floor.

    If a model loses boxed stages -- a glyph added, a stage merged -- and the
    number here stays, the ratchet is holding a gap open for a regeneration to
    fill without firing. Lower it.
    """
    now = _boxed_shape_stages()
    slack = {k: (v, now.get(k, 0)) for k, v in BOXED_SHAPE_STAGES.items()
             if now.get(k, 0) < v}
    assert not slack, (
        "the baseline is above what the specs now hold: "
        + ", ".join(f"{k} baseline {was}, actually {is_}"
                    for k, (was, is_) in sorted(slack.items()))
        + ".\nLower it, or the difference is room to drift back without failing.")
