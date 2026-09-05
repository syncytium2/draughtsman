"""Stage 5 — the check that can fail.

SPEC.md §5: every traced node must be accounted for in exactly one stage. Not
zero, not two. It is precisely what pytorch-graph lacked: it dropped five whole
stages and reported success.

IT IS THE FIRST ASSERTION HERE, NOT THE ONLY ONE. Coverage answers "was an
operation dropped" and nothing else. Five failures have now passed it while
something was wrong that it does not look at: a parameter counted twice, an arrow
nobody checked, a reference with two answers, a format the agent was never told
about, and this very count derived a second time in the browser. Three of those
put a false statement in a figure; the others left it true and unreadable, or
misreported the check itself. The rest of the assertions live beside this one in
this module and in facts.py. DECISIONS.md correction 5 names the pattern; do not
restore the claim that this one is sufficient.

What this does NOT verify: that the names are good, the grouping is natural, or
the figure is legible. Those need a human, and :func:`report` says so out loud so
a green check is never read as a good figure.
"""

from __future__ import annotations

from dataclasses import dataclass

from draughtsman.facts import (BATCHED_SHAPE_FIELDS, FactError, Graph, REF_RE,
                               bare_numbers, repeat_counts, resolve)
from draughtsman.spec import Spec, length_pt


@dataclass
class Counts:
    """The §5 arithmetic, computed once, here.

    THERE IS ONE PLACE THAT COUNTS COVERAGE. Anything that displays it -- the CLI
    report, the UI badge -- reads these numbers rather than deriving its own. A
    second implementation is how an indicator ends up disagreeing with the check
    it indicates, and this indicator is the first thing a reader trusts about a
    figure. Deriving it twice is itself an instance of the pattern in DECISIONS.md
    correction 5, and is how this one read 48/47.
    """
    traced: int = 0        # traced nodes, which is what coverage ranges over
    exactly_once: int = 0  # ... in exactly one stage or elision. §5's condition.
    elided: int = 0
    duplicated: int = 0    # in two or more places
    unplaced: int = 0
    untraced_claimed: int = 0   # model inputs a stage names; never counted above

    def as_dict(self) -> dict:
        return {
            "traced": self.traced, "exactly_once": self.exactly_once,
            "elided": self.elided, "duplicated": self.duplicated,
            "unplaced": self.unplaced, "untraced_claimed": self.untraced_claimed,
        }


@dataclass
class Result:
    errors: list[str]
    warnings: list[str]
    notes: list[str]
    counts: Counts

    @property
    def ok(self) -> bool:
        return not self.errors


def check(spec: Spec, graph: Graph) -> Result:
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []

    stages = {s.id: s.nodes for s in spec.stages}

    # -- stage ids ------------------------------------------------------------
    seen: set[str] = set()
    for s in spec.stages:
        if s.id in seen:
            errors.append(f"duplicate stage id {s.id!r}")
        seen.add(s.id)

    # -- coverage: exactly one, never zero, never two -------------------------
    owner: dict[str, list[str]] = {}
    for s in spec.stages:
        for nid in s.nodes:
            owner.setdefault(nid, []).append(f"stage {s.id!r}")
    for e in spec.elided:
        for nid in e.nodes:
            owner.setdefault(nid, []).append("elided")

    for nid, places in sorted(owner.items()):
        if nid not in graph.nodes:
            errors.append(f"{places[0]} claims node {nid!r}, which graph.json "
                          "does not have")
        elif len(places) > 1:
            node = graph.nodes[nid]
            errors.append(f"node {nid} ({node['kind']}) appears in "
                          f"{len(places)} places: {', '.join(places)}")

    uncovered = [n for n in graph.traced if n not in owner]
    for nid in uncovered:
        node = graph.nodes[nid]
        where = node.get("module") or _where(node)
        errors.append(f"node {nid} ({node['kind']}{f' at {where}' if where else ''}) "
                      "is in no stage and is not elided")

    # -- elision is a decision, so it must carry a reason ---------------------
    for e in spec.elided:
        if not e.reason.strip():
            errors.append(f"elision of {', '.join(e.nodes)} has no reason")

    # -- edges reference real stages, and the stage graph is acyclic ----------
    for e in spec.edges:
        for end, sid in (("from", e.src), ("to", e.dst)):
            if sid not in stages:
                errors.append(f"edge {end}={sid!r} names no stage")
    if not errors:
        cyc = _cycle([s.id for s in spec.stages],
                     [(e.src, e.dst) for e in spec.edges])
        if cyc:
            errors.append("stage graph has a cycle: " + " -> ".join(cyc))

    # -- the arrows, against the trace ----------------------------------------
    #
    # COVERAGE CHECKS PLACEMENT, NOT TOPOLOGY, AND THAT IS A HOLE. Every node
    # being in exactly one stage says nothing about the arrows between the
    # stages, and the arrows are most of what a reader takes from the figure.
    # `tensor_inputs` already records each node's nearest substantive ancestors,
    # so the traced stage-to-stage topology is derivable here with no help from
    # the tracer: an edge T -> S exists iff some node of S consumes some node of T.
    if not errors:
        traced_edges = _traced_edges(spec, graph)
        drawn = {(e.src, e.dst) for e in spec.edges}

        # An arrow with nothing under it is the figure asserting a data path the
        # model does not have -- a claim, not an omission, so it is an error. It
        # can be declared instead, the way a dropped node can be elided.
        for e in spec.edges:
            if (e.src, e.dst) in traced_edges:
                continue
            if e.untraced:
                notes.append(f"edge {e.src} -> {e.dst} is drawn but not traced, "
                             f"declared: {e.untraced}")
            else:
                errors.append(
                    f"edge {e.src} -> {e.dst} is drawn but no node of {e.dst!r} "
                    f"consumes any node of {e.src!r}. Either it is wrong, or it "
                    "is a path the model has and the trace does not — say which "
                    'with "untraced": "<reason>" on the edge.')

        # The other direction cannot be an error. Many real dependencies are
        # SHAPE dependencies a reader does not want drawn -- `randn_like` reading
        # a mean's shape, a slice reading a sequence length -- and collapsing a
        # repeated block into one stage legitimately buries fan-out inside it.
        # But some are the architecture: whisper's every decoder block reads the
        # audio, and a figure showing only the first understates the model.
        for src, dst in sorted(traced_edges - drawn):
            warnings.append(
                f"{src} -> {dst} is in the trace and not in the figure. If that "
                "is a shape dependency a reader does not need, leave it; if it "
                "is a data path, the figure is understating the model.")

    # -- a claimed repetition must be one -------------------------------------
    counts = repeat_counts(spec.stages, graph) if not errors else {}
    ids = {s.id for s in spec.stages}
    for s in spec.stages:
        if not s.repeat:
            continue
        missing = [t for t in s.repeat.template if t not in ids]
        if missing:
            errors.append(f"stage {s.id!r}: repeat template names no stage: "
                          + ", ".join(sorted(missing)))
            continue
        if s.id in s.repeat.template:
            errors.append(f"stage {s.id!r}: repeat template includes itself")
            continue
        n = counts.get(s.id)
        if n is None:
            unit = sum(len(t.nodes) for t in spec.stages
                       if t.id in s.repeat.template)
            errors.append(
                f"stage {s.id!r} claims to repeat "
                f"{' + '.join(s.repeat.template)}, but its {len(s.nodes)} nodes "
                f"are not a whole number of copies of that {unit}-node unit, or "
                "the operations differ. A repetition the graph does not contain "
                "must not be drawn as one — regroup, or drop the claim.")
        elif n < 2:
            warnings.append(
                f"stage {s.id!r} repeats its template once, which is not a "
                "repetition. Draw it like any other stage.")
        else:
            notes.append(f"stage {s.id!r} verified as {n} copies of "
                         + " + ".join(s.repeat.template))

    # -- every reference resolves, and lane counts agree with the model -------
    for s in spec.stages:
        for text in [s.name, *(s.detail or []), s.note or ""]:
            if not text:
                continue
            try:
                resolve(text, graph, node_ids=s.nodes, stages=stages,
                        where=f"stage {s.id!r}", stage_id=s.id,
                        repeats=counts)
            except FactError as exc:
                errors.append(str(exc))
        bare = [b for text in [s.name, *(s.detail or [])] if text
                for b in bare_numbers(text)]
        if bare:
            warnings.append(
                f"stage {s.id!r} writes the literal number(s) {', '.join(bare)} in "
                "its own text — a fact in the figure that did not come from "
                "graph.json. Use a {reference} unless it is part of a name.")
        if s.glyph:
            try:
                resolve(s.glyph.of, graph, node_ids=s.nodes, stages=stages,
                        where=f"stage {s.id!r}")
            except FactError as exc:
                errors.append(str(exc))
            if s.glyph.scale not in ("sqrt", "linear"):
                errors.append(
                    f"stage {s.id!r}: glyph scale {s.glyph.scale!r} is neither "
                    "'sqrt' nor 'linear'.")
            # A STYLE NOBODY IMPLEMENTS RENDERS AS A BLOCK AND PASSES. `scale`
            # was validated here from the start and `style` never was, so
            # `"blcok"` -- or a style proposed in a design and not yet built --
            # draws the default silently and `check` calls it correct. That is a
            # figure disagreeing with its spec while every assertion is green,
            # which is the one thing this file exists to prevent.
            if s.glyph.style not in ("block", "marks", "sheets"):
                errors.append(
                    f"stage {s.id!r}: glyph style {s.glyph.style!r} is not one "
                    "of 'block', 'marks' or 'sheets'. An unknown style would be "
                    "drawn as a block, and the figure would not be the spec.")
            # RANK IS SET BY THE STYLE, AND ONLY `sheets` MAY TAKE THREE.
            #
            # The two-axis rule is not arbitrary: the eye reads a rectangle's
            # area, so both edges must come from one tensor or the reader
            # perceives a product that means nothing. `sheets` is read as a
            # VOLUME — face area times stack depth — so three axes of one tensor
            # multiply to something real in the same way. Every other style stays
            # at two, because nothing in a rectangle can carry a third.
            want = 3 if s.glyph.style == "sheets" else 2
            if len(s.glyph.axes) != want or len(s.glyph.labels) != want:
                named = ("one for depth, one for height, one for width"
                         if want == 3 else
                         "one for height, one for width")
                errors.append(
                    f"stage {s.id!r}: a {s.glyph.style!r} glyph needs exactly "
                    f"{want} axes and {want} labels — {named}.")

        for meter in s.meters:
            try:
                text = resolve(meter.value, graph, node_ids=s.nodes,
                               stages=stages, where=f"stage {s.id!r}")
                float(text.replace(",", ""))
            except FactError as exc:
                errors.append(str(exc))
            except ValueError:
                errors.append(
                    f"stage {s.id!r}: meter {meter.label!r} resolves to {text!r}, "
                    "which is not a number. A bar drawn from a shape string would "
                    "be drawing the length of the string.")

        if s.lanes:
            try:
                count = int(resolve(s.lanes.count_from, graph, node_ids=s.nodes,
                                    stages=stages, where=f"stage {s.id!r} lanes"))
            except (FactError, ValueError) as exc:
                errors.append(f"stage {s.id!r}: lanes.count_from -> {exc}")
            else:
                if s.lanes.labels and len(s.lanes.labels) != count:
                    errors.append(
                        f"stage {s.id!r} labels {len(s.lanes.labels)} lanes but "
                        f"{s.lanes.count_from} resolves to {count}")

    # ONE SCALE MEANS ONE MEANING. Glyphs share a figure-wide scale, so two
    # stages labelling their axes differently are drawing incomparable rectangles
    # on a common ruler — the reader has no way to see that and every reason to
    # compare them.
    glyphed = [s for s in spec.stages if s.glyph]
    labelling = {tuple(s.glyph.labels) for s in glyphed}
    if len(labelling) > 1:
        errors.append(
            "glyphs in one figure must label their axes the same way; found "
            + " and ".join(repr(" × ".join(l)) for l in sorted(labelling)))
    scaling = {s.glyph.scale for s in glyphed}
    if len(scaling) > 1:
        errors.append(
            "glyphs in one figure must use one scale; found "
            + " and ".join(sorted(repr(x) for x in scaling)))
    # WILL THIS BE LEGIBLE AT THE SIZE IT IS PRINTED?
    #
    # The last question in this file that coverage cannot ask. A figure with a
    # stated output width has a unit budget, and going over it does not fail
    # anything at render time — the SVG scales down happily and takes the type
    # with it. Measured across the gallery before this existed: at a 6in double
    # column the detail type landed between 2.49pt and 5.25pt, and no figure in
    # the set cleared 6pt anywhere.
    #
    # Imported here rather than at module scope: `check` is the layer that must
    # not need a renderer to answer a question about coverage, and this is the
    # one question that genuinely does.
    if spec.output.width:
        from draughtsman.render import render, width_budget, type_pt
        import re as _re
        try:
            drawn = render(spec, graph)
            units = float(_re.search(r'viewBox="0 0 ([\d.]+)', drawn).group(1))
        except Exception as exc:                      # a broken spec fails elsewhere
            units = 0.0
            errors.append(f"output.width is set but the figure did not render: {exc}")
        if units:
            got = type_pt(spec, units)
            floor = length_pt(spec.output.min_type, "output.min_type")
            if got is not None and got >= floor:
                # THE PASSING CASE WAS SILENT TOO, which is half the same defect.
                # A gate that reports only its failures cannot be told apart from
                # a gate that is switched off, so the reader of a green run
                # learned nothing about which of the two they had. This says the
                # number it measured, so "checked and cleared" and "not checked"
                # read differently at a glance.
                notes.append(
                    f"legibility: smallest type is {got:.2f}pt at "
                    f"{spec.output.width}, clearing the {spec.output.min_type} "
                    f"floor. The figure is {units:.0f} units wide.")
            if got is not None and got < floor:
                budget = width_budget(spec)
                errors.append(
                    f"at {spec.output.width} the smallest type would be "
                    f"{got:.2f}pt, under the {spec.output.min_type} floor. The "
                    f"figure is {units:.0f} units wide and the budget is "
                    f"{budget:.0f}. Narrow it — wrap the spine into more rows "
                    f"(layout.wrap around {budget * 0.92:.0f}), drop a detail "
                    f"line, or collapse a stage. Do not shrink the type: the "
                    f"floor is the point.")
    else:
        # A GATE THAT DID NOT RUN LOOKS EXACTLY LIKE A GATE THAT PASSED, and this
        # is the one place in the file where that is true by construction: every
        # other question above is asked of every spec, and this one is asked only
        # of a spec that opted in. So a figure whose type would print at 2.49pt
        # produces the same clean green run as one that was measured and cleared
        # its floor.
        #
        # An outside review found it by setting the field on the specs that lack
        # it and re-running: "they pass check only because the field that would
        # catch it is absent." That is the shape of the defect this repository
        # convicts other tools of -- a confident answer to a question nobody
        # asked -- arriving in its own gate.
        #
        # A WARNING AND NOT AN ERROR, deliberately. Opting out is legal: a figure
        # for a slide or a README has no printed size to be measured against, and
        # forcing a declaration would make the field a formality rather than a
        # claim. What is not legal is saying nothing.
        warnings.append(
            "output.width is not set, so THE LEGIBILITY GATE DID NOT RUN. This "
            "figure has not been checked at any printed size, and coverage "
            "passing says nothing about it. Set output.width and "
            'output.min_type (e.g. "6in" and "6pt") to turn it on. To ask the '
            "same question about the rendered file without editing the spec: "
            "tools/measure_type.py --print 6in --floor 6pt <figure.svg>")

    if spec.layout.chrome not in ("box", "none"):
        errors.append(
            f"layout chrome {spec.layout.chrome!r} is neither 'box' nor 'none'. "
            "An unknown value would draw the boxed figure, and the figure would "
            "not be the spec.")
    # AND ONE STYLE, for the same reason one rank. A figure mixing `sheets` with
    # `block` would put a rectangle and a volume on one ruler, and the styles do
    # not even agree on how many axes they read — so the shared scale would be
    # computed over glyphs measuring different things.
    styling = {s.glyph.style for s in glyphed}
    if len(styling) > 1:
        errors.append(
            "glyphs in one figure must use one style; found "
            + " and ".join(sorted(repr(x) for x in styling)))
    if len(glyphed) == 1:
        warnings.append(
            f"stage {glyphed[0].id!r} is the only one with a glyph, so its "
            "rectangle is the full scale by definition and shows nothing a "
            "reader can weigh against anything.")

    # A RECTANGLE AROUND A RECTANGLE, WHICH WAS PROSE ON THE PAGE UNTIL NOW.
    # DECISIONS.md, "What the page leads with": a box is the right container when
    # the stage's content is words and the wrong one when the content is a
    # drawing of the tensor -- the two compete for the same reading and the eye
    # settles on the larger, which is the box. `chrome` is a field of the stage
    # now, so this is answerable per stage and no longer forces a figure to
    # choose one container for everything it holds.
    #
    # A WARNING AND NOT AN ERROR. `resnet` ships this way and is not wrong about
    # its model; refusing it would refuse a committed figure over a judgement the
    # spec is entitled to make. A warning names it and leaves the call where it
    # belongs.
    boxed = [s.id for s in glyphed
             if (s.chrome or spec.layout.chrome) != "none"]
    if boxed:
        warnings.append(
            "glyph inside a box: " + ", ".join(repr(x) for x in sorted(boxed))
            + ". The box is a second rectangle around the drawing and the eye "
            "reads the larger one. Set chrome to 'none' on those stages to let "
            "the tensor be the stage, or take the glyph off.")

    # A BAR THAT COMPARES WITH NOTHING IS DECORATION. Meters are drawn on a
    # scale shared by every stage carrying the same label, so a series with one
    # member is a bar whose only information is that it is full.
    series: dict[str, list[str]] = {}
    for s in spec.stages:
        for meter in s.meters:
            series.setdefault(meter.label, []).append(s.id)
    for label, holders in sorted(series.items()):
        if len(holders) == 1:
            warnings.append(
                f"meter {label!r} appears on one stage ({holders[0]}), so its bar "
                "is full by definition and compares with nothing. Put it on the "
                "stages a reader should weigh against each other, or write the "
                "number in `detail` instead.")

    for text in [spec.title, spec.subtitle or "", spec.caption or ""]:
        if text:
            try:
                resolve(text, graph, stages=stages, where="title")
            except FactError as exc:
                errors.append(str(exc))

    # -- a hidden axis must be 1, or hiding it deletes information --------------
    #
    # `batch_axis` lets a figure stop drawing an axis that carries nothing. That
    # is only true while the axis IS 1. `tube` reshapes to [30, 1, 600] midway --
    # cells folded into the batch -- and a figure that dropped that leading 30
    # would delete the cell count and say nothing about it. So the declaration is
    # checked against every shape the figure actually renders, not assumed.
    if spec.batch_axis is not None:
        ba = spec.batch_axis
        # Every text the figure draws, not just the stages: the title resolves
        # {model.input_shape} through the same hiding, and a claim that nothing
        # checks is decoration (DECISIONS.md correction 5).
        checked = [(s_, t) for s_ in spec.stages
                   for t in [s_.name, *(s_.detail or [])]]
        checked += [(None, t) for t in
                    (spec.title, spec.subtitle or "", spec.caption or "")]
        for s_, text in checked:
                if not text:
                    continue
                for ref in REF_RE.findall(text):
                    body = ref.strip()
                    head, _, rest = body.partition(".")
                    path = [p for p in rest.split(".") if p] if rest else []
                    if not path or path[-1].partition("[")[0] not in \
                            BATCHED_SHAPE_FIELDS or path[-1].endswith("]"):
                        continue
                    try:
                        if head == "stage":
                            if s_ is None:
                                continue        # not addressable from a title
                            val = graph.stage_fact(s_.nodes, path)
                        elif head.startswith("node:"):
                            val = graph.node_fact(head[5:], path)
                        elif head == "model":
                            val = graph.model_fact(path)
                        else:
                            continue
                    except FactError:
                        continue        # already reported by the resolver above
                    if isinstance(val, list) and -len(val) <= ba < len(val) \
                            and val[ba] != 1:
                        errors.append(
                            f"{f'stage {s_.id!r}' if s_ else 'the title'} is drawn "
                            f"with batch_axis {ba} and shows "
                            f"{{{body}}}, whose axis {ba} is {val[ba]}, not 1. "
                            "Hiding it would delete a number the reader needs — "
                            "drop the declaration, or do not draw this shape.")

    # -- a glyph's axes shift under a batch declaration, and its labels cannot --
    #
    # `glyph.axes` is a positional index into a shape whose RANK depends on
    # `batch_axis`, declared elsewhere in the same spec. U-Net's `axes: [1, 2]`
    # with `labels: ["channels", "height"]` means (channels, height) on a
    # four-axis shape and (height, width) once the batch is hidden -- every
    # rectangle becomes a square, the constant-area finding the figure exists for
    # disappears, and NOTHING ERRORS, because both indices are still in range.
    # (Three-axis shapes fall off the end and raise, which is why a rank-three
    # model was safe and U-Net was not. Loud at rank three, silent at rank four.)
    #
    # Nothing here can verify the labels -- they are the agent's words and only
    # they say what an axis means. What IS checkable is that NEGATIVE indices do
    # not move: hiding a LEADING axis leaves every trailing position where it
    # was, so `[-3, -2]` picks the same pair before and after. Positive indices
    # into the drawn shape are legitimate, so this is a warning and not an error;
    # what it catches is the spec that had a glyph BEFORE the declaration was
    # added, where the indices silently came to mean something else.
    if spec.batch_axis is not None:
        for s_ in spec.stages:
            if s_.glyph and any(i >= 0 for i in s_.glyph.axes):
                warnings.append(
                    f"stage {s_.id!r} declares batch_axis {spec.batch_axis} and "
                    f"its glyph indexes axes {list(s_.glyph.axes)} positively. "
                    "Those index the shape AS DRAWN, so if the declaration was "
                    "added after the glyph they now name different axes and the "
                    "labels no longer describe them. Negative indices count from "
                    "the end and do not move when a leading axis is hidden.")

    # -- a traced constant may be an initialisation, and the trace cannot say ---
    #
    # `tube`'s max-pool width is `2 * kmin + 1` with kmin read off a TRAINED
    # parameter. `int()` on a tensor leaves tensor-land for Python, so the width
    # reaches the graph as a bare literal and draughtsman drew "max-pool, width
    # 3" -- true of an untrained model and of nothing else. torch says so at
    # trace time and tracing.py now records it; this is where saying so has
    # teeth.
    #
    # THE RULE IS NOT "constants ARE SUSPECT". It is: when the tracer reports it
    # baked a Python value, a spec may still quote a traced constant, but it has
    # to say WHY that one is architectural. The trace cannot answer it -- the data
    # flow is severed, so no walk of graph.json recovers which constant came from
    # where -- and a hand-maintained list of design quantities would go stale
    # exactly when the model moved. A line per reference, in the spec, is a
    # decision in a diff. It is the same shape as an explicit elision, for the
    # same reason.
    if graph.model_hazards:
        used = sorted({
            ref for s in spec.stages
            for text in [s.name, *(s.detail or [])] if text
            for ref in _constant_refs(text)
        })
        for text in [spec.title, spec.subtitle or "", spec.caption or ""]:
            used = sorted(set(used) | set(_constant_refs(text or "")))
        where = ", ".join(f"{h['file']}:{h['line']}" for h in graph.model_hazards)
        unacknowledged = [r for r in used if not spec.constants.get(r, "").strip()]
        for ref in unacknowledged:
            errors.append(
                f"the figure quotes the traced constant {{{ref}}}, and the tracer "
                f"reports it baked a Python value out of a tensor at {where}. A "
                "constant may therefore be an initialisation rather than an "
                "architectural quantity, and graph.json cannot tell which. Add "
                f'"constants": {{"{ref}": "<why this one is architectural>"}} to '
                "the spec, or stop quoting it.")
        stale = sorted(set(spec.constants) - set(used))
        for ref in stale:
            warnings.append(
                f"spec declares constant {ref!r} architectural, but no text quotes "
                "it — a justification for a fact the figure no longer states")
        if not used:
            notes.append(f"the tracer baked a Python value at {where}; the figure "
                         "quotes no traced constant")
        elif not unacknowledged:
            notes.append(f"the tracer baked a Python value at {where}; "
                         f"{len(used)} traced constant(s) quoted, each declared "
                         "architectural by the spec")
    elif graph.hazards:
        # Recorded, and all of it inside torch. Worth saying, because "no hazard"
        # and "a hazard that is not about your model" should not read the same.
        notes.append(
            f"{len(graph.hazards)} bake hazard(s), all inside torch itself "
            f"({', '.join(sorted({h['file'] for h in graph.hazards}))}) — how a "
            "stock module was constructed, not a fitted quantity in this model")
    elif not graph.hazards_recorded:
        warnings.append(
            "graph.json predates hazard recording, so a quoted constant that is "
            "really an initialisation would not be caught here. Re-trace to check.")

    # -- parameters ------------------------------------------------------------
    total = graph.model["params"]
    covered = sum(graph.nodes[n]["params"] for s in spec.stages for n in s.nodes
                  if n in graph.nodes)
    dropped = sum(graph.nodes[n]["params"] for e in spec.elided for n in e.nodes
                  if n in graph.nodes)
    traced = set(graph.traced)
    counts = Counts(
        traced=len(traced),
        exactly_once=sum(1 for n in traced if len(owner.get(n, [])) == 1),
        elided=sum(1 for e in spec.elided for n in e.nodes if n in traced),
        duplicated=sum(1 for n in traced if len(owner.get(n, [])) > 1),
        unplaced=len(uncovered),
        untraced_claimed=sum(1 for n in owner if n not in traced
                             and n in graph.nodes),
    )
    notes.append(f"{counts.traced} traced nodes, {counts.exactly_once} in exactly "
                 f"one place, {counts.elided} of those elided")
    if counts.untraced_claimed:
        notes.append(f"{counts.untraced_claimed} model input(s) named by a stage — "
                     "addressable, and not something coverage ranges over")
    notes.append(f"{covered} of {total} parameters reach a drawn stage")
    if dropped:
        warnings.append(f"{dropped} parameter(s) are in elided nodes and appear "
                        "nowhere in the figure")
    if not graph.doc.get("params_fully_attributed", True):
        warnings.append(
            f"graph.json attributes {graph.doc.get('params_attributed')} of "
            f"{total} parameters to nodes; the rest can never be drawn")

    return Result(errors=errors, warnings=warnings, notes=notes, counts=counts)


def _constant_refs(text: str) -> list[str]:
    """The ``node:<id>.constants.<name>`` references in *text*, without braces."""
    out = []
    for m in REF_RE.finditer(text):
        body = m.group(1).strip()
        if body.startswith("node:") and ".constants." in body:
            out.append(body[len("node:"):])
    return out


def _where(node: dict) -> str:
    src = node.get("source")
    if not src:
        return ""
    return f"{src['file']}:{src['line']}"


def _cycle(nodes: list[str], edges: list[tuple[str, str]]) -> list[str]:
    succ: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in edges:
        succ.setdefault(a, []).append(b)
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {n: WHITE for n in succ}
    path: list[str] = []

    def visit(n: str) -> list[str]:
        colour[n] = GREY
        path.append(n)
        for m in succ.get(n, []):
            if colour.get(m) == GREY:
                return path[path.index(m):] + [m]
            if colour.get(m, WHITE) == WHITE:
                found = visit(m)
                if found:
                    return found
        path.pop()
        colour[n] = BLACK
        return []

    for n in nodes:
        if colour[n] == WHITE:
            found = visit(n)
            if found:
                return found
    return []


# LEGIBILITY LEFT THIS SENTENCE WHEN IT STOPPED BEING TRUE OF EVERY RUN. The
# caveat used to say coverage says nothing about whether the figure is legible,
# and printed directly under a line reporting the measured point size — a
# contradiction in one screen of output. It is now conditional in the same way
# the gate is: checked where `output.width` is set, reported above when it runs,
# and named as absent by a warning when it does not.
CAVEAT = (
    "Coverage passing means no traced operation was silently dropped. It says "
    "NOTHING about whether the names are good or the grouping is natural. "
    "Legibility is checked only where output.width is set, and reported above "
    "when it is. A person still has to look at it."
)


def summary(counts: Counts) -> str:
    """One line, used by the CLI and by the UI badge. Says the failure, not just
    a ratio: `47/47` while a node sits in two stages would read as success."""
    out = f"{counts.exactly_once}/{counts.traced} in exactly one place"
    if counts.duplicated:
        out += f" · {counts.duplicated} in two"
    if counts.unplaced:
        out += f" · {counts.unplaced} unplaced"
    return out


def report(result: Result) -> str:
    lines = []
    for note in result.notes:
        lines.append(f"  {note}")
    for w in result.warnings:
        lines.append(f"  warning: {w}")
    for e in result.errors:
        lines.append(f"  ERROR: {e}")
    lines.append("")
    lines.append(summary(result.counts))
    if result.ok:
        lines.append("coverage OK — every traced node is in exactly one stage.")
        lines.append(CAVEAT)
    else:
        lines.append(f"coverage FAILED — {len(result.errors)} error(s).")
    return "\n".join(lines)


def _traced_edges(spec: Spec, graph: Graph) -> set[tuple[str, str]]:
    """Stage-to-stage dependencies as the TRACE has them.

    Derived from `tensor_inputs`, which graph.json already carries, so this needs
    nothing from the tracer. Stages that name a model input participate: the
    input is addressable and a stage may own it.
    """
    owner: dict[str, str] = {}
    for s in spec.stages:
        for nid in s.nodes:
            owner[nid] = s.id
    elided = {n for e in spec.elided for n in e.nodes}

    # AN ELIDED NODE IS TRANSPARENT, NOT ABSENT. Eliding says a reader does not
    # need to see an operation; it does not say the data stopped flowing through
    # it. A model that elides both of its permutes had its input arrow reported
    # as unbacked -- the check calling a correct figure wrong, which
    # is how a check gets switched off. So resolve through them to the stages
    # behind, the way `tensor_inputs` already sees through structural nodes.
    def sources(nid: str, seen: frozenset[str]) -> set[str]:
        node = graph.nodes.get(nid)
        if not node or nid in seen:
            return set()
        seen = seen | {nid}
        out: set[str] = set()
        for anc in node.get("tensor_inputs") or []:
            if anc in owner:
                out.add(owner[anc])
            elif anc in elided:
                out |= sources(anc, seen)
        return out

    edges: set[tuple[str, str]] = set()
    for s in spec.stages:
        for nid in s.nodes:
            node = graph.nodes.get(nid)
            if not node:
                continue
            for anc in node.get("tensor_inputs") or []:
                if anc in owner:
                    if owner[anc] != s.id:
                        edges.add((owner[anc], s.id))
                elif anc in elided:
                    for src in sources(anc, frozenset()):
                        if src != s.id:
                            edges.add((src, s.id))
    return edges
