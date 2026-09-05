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

WHAT IS NOT CHECKED HERE, and both are recorded in DECISIONS.md rather than left
to be rediscovered. `chrome` is a figure-level field, so the per-stage rule
cannot yet be expressed and `tube` draws marks inside boxes -- named below as the
one exemption, so that anything new fails. And "every boxed stage either has word
content or carries a written reason" is not mechanisable: a machine cannot tell
whether a stage's content is words, and the nearest proxy fires on 55 stages in
this repository, most of them correctly boxed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "index.html"

# `tube` draws `marks` glyphs inside boxes. Making the whole figure bare would
# strip the boxes off its word stages, which the decision forbids in the other
# direction, so the fix is `chrome` per stage and it is its own change.
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
