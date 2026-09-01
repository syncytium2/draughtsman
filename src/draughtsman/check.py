"""Stage 5 — the check that can fail.

SPEC.md §5: every traced node must be accounted for in exactly one stage. Not
zero, not two. This is the entire safety argument for letting an agent into the
pipeline, and it is precisely what pytorch-graph lacked: it dropped five whole
stages and reported success.

What this does NOT verify: that the names are good, the grouping is natural, or
the figure is legible. Those need a human, and :func:`report` says so out loud so
a green check is never read as a good figure.
"""

from __future__ import annotations

from dataclasses import dataclass

from draughtsman.facts import FactError, Graph, bare_numbers, resolve
from draughtsman.spec import Spec


@dataclass
class Counts:
    """The §5 arithmetic, computed once, here.

    THERE IS ONE PLACE THAT COUNTS COVERAGE. Anything that displays it -- the CLI
    report, the UI badge -- reads these numbers rather than deriving its own. A
    second implementation is how an indicator ends up disagreeing with the check
    it indicates, and this indicator is the entire safety argument for letting an
    agent into the pipeline.
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

    # -- every reference resolves, and lane counts agree with the model -------
    for s in spec.stages:
        for text in [s.name, *(s.detail or []), s.note or ""]:
            if not text:
                continue
            try:
                resolve(text, graph, node_ids=s.nodes, stages=stages,
                        where=f"stage {s.id!r}")
            except FactError as exc:
                errors.append(str(exc))
        bare = [b for text in [s.name, *(s.detail or [])] if text
                for b in bare_numbers(text)]
        if bare:
            warnings.append(
                f"stage {s.id!r} writes the literal number(s) {', '.join(bare)} in "
                "its own text — a fact in the figure that did not come from "
                "graph.json. Use a {reference} unless it is part of a name.")
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

    for text in [spec.title, spec.subtitle or "", spec.caption or ""]:
        if text:
            try:
                resolve(text, graph, stages=stages, where="title")
            except FactError as exc:
                errors.append(str(exc))

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


CAVEAT = (
    "Coverage passing means no traced operation was silently dropped. It says "
    "NOTHING about whether the names are good, the grouping is natural, or the "
    "figure is legible. A person still has to look at it."
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
