"""Stage 3a — layout. Deterministic, and ours.

Sugiyama, in the small: rank by longest path, insert a dummy per rank an edge
skips, order within rank by barycentre, then place. Roughly 200 lines, no system
binary, and byte-identical for the same input on any machine — which is what lets
SPEC.md §6's staleness test be a plain equality assertion instead of a test that
skips when graphviz is missing.

THE DUMMIES ARE THE POINT, not an implementation detail. An edge that skips a rank
— `tube`'s bypass, which leaves the mean and rejoins at the concat two stages
later — gets a placeholder of real height at every rank it crosses, so the ranks
part to let it through. That is the fix for the failure SPEC.md §4 records from
the hand-laid original: lane labels struck through by the figure's own edges,
invisible in the source and obvious in the render. Here it cannot happen, because
the edge reserved its own space before anything was drawn.

Nothing about this is hand placement. The objection that started this repo is
coordinates typed per figure; these are derived from topology, once, for any
graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Box:
    id: str
    w: float
    h: float
    rank: int = 0
    order: int = 0
    x: float = 0.0
    y: float = 0.0          # centre
    dummy: bool = False


@dataclass
class Route:
    src: str
    dst: str
    points: list[tuple[float, float]] = field(default_factory=list)
    label: str | None = None
    style: str = "solid"


@dataclass
class Drawing:
    boxes: dict[str, Box]
    routes: list[Route]
    width: float
    height: float


DUMMY_H = 12.0


def rank_nodes(ids: list[str], edges: list[tuple[str, str]]) -> dict[str, int]:
    """Longest path from a source. Assumes acyclic — `check` proves that."""
    preds: dict[str, list[str]] = {i: [] for i in ids}
    succs: dict[str, list[str]] = {i: [] for i in ids}
    for a, b in edges:
        succs[a].append(b)
        preds[b].append(a)

    rank = {i: 0 for i in ids}
    # ids arrive in spec order, which for a sane spec is already topological;
    # iterate to a fixed point so it need not be.
    for _ in range(len(ids) + 1):
        changed = False
        for i in ids:
            want = max((rank[p] + 1 for p in preds[i]), default=0)
            if want != rank[i]:
                rank[i] = want
                changed = True
        if not changed:
            break
    return rank


def _initial_order(ids, edges, rank) -> dict[str, int]:
    """Depth-first from the sources, in the order the spec declares its edges.

    So a hand edit that reorders the edges reorders the lanes, predictably. That
    is the whole knob a human gets over vertical arrangement, and it is worth
    more than a better prompt (SPEC.md §8.3).
    """
    succs: dict[str, list[str]] = {i: [] for i in ids}
    indeg = {i: 0 for i in ids}
    for a, b in edges:
        succs[a].append(b)
        indeg[b] += 1

    order: dict[int, list[str]] = {}
    seen: set[str] = set()

    def visit(n: str):
        if n in seen:
            return
        seen.add(n)
        order.setdefault(rank[n], []).append(n)
        for m in succs[n]:
            visit(m)

    for i in ids:
        if indeg[i] == 0:
            visit(i)
    for i in ids:            # anything unreachable still gets a place
        visit(i)

    return {n: k for lane in order.values() for k, n in enumerate(lane)}


def _by_rank(boxes: dict[str, Box]) -> dict[int, list[Box]]:
    ranks: dict[int, list[Box]] = {}
    for b in boxes.values():
        ranks.setdefault(b.rank, []).append(b)
    for lane in ranks.values():
        lane.sort(key=lambda b: (b.order, b.id))
    return ranks


def _barycentre(boxes, edges, sweeps: int = 6) -> None:
    preds: dict[str, list[str]] = {i: [] for i in boxes}
    succs: dict[str, list[str]] = {i: [] for i in boxes}
    for a, b in edges:
        succs[a].append(b)
        preds[b].append(a)

    for sweep in range(sweeps):
        ranks = _by_rank(boxes)
        keys = sorted(ranks)
        if sweep % 2:
            keys.reverse()
        for r in keys:
            neigh = preds if sweep % 2 == 0 else succs
            lane = ranks[r]
            scored = []
            for k, b in enumerate(lane):
                ns = [boxes[n].order for n in neigh[b.id] if n in boxes]
                scored.append((sum(ns) / len(ns) if ns else float(b.order), k, b))
            scored.sort(key=lambda t: (t[0], t[1]))
            for k, (_, _, b) in enumerate(scored):
                b.order = k


def _place(boxes, edges, *, hgap: float, vgap: float, passes: int = 32) -> None:
    ranks = _by_rank(boxes)

    x = 0.0
    for r in sorted(ranks):
        lane = ranks[r]
        widest = max(b.w for b in lane)
        for b in lane:
            b.x = x + (widest - b.w) / 2.0
        x += widest + hgap

    for lane in ranks.values():                     # initial stack, centred on 0
        total = sum(b.h for b in lane) + vgap * (len(lane) - 1)
        y = -total / 2.0
        for b in lane:
            b.y = y + b.h / 2.0
            y += b.h + vgap

    # WHY THE SPINE COMES OUT STRAIGHT. Textbook Sugiyama straightens the dummy
    # chains first, so long edges run level and the real nodes bend around them.
    # For a figure that is backwards: a reader follows the main path, and it is
    # the skipping edge -- the bypass -- that should bow out of the way.
    #
    # So a real stage is positioned by its real neighbours ONLY. Dummies are
    # positioned by whatever they touch, and are then pushed clear by the
    # separation pass, which is what reserves the bypass its own space. Merely
    # down-weighting the dummies is not enough: any weight at all leaves a
    # residual pull, and the chain settles a few pixels crooked.
    preds: dict[str, list[str]] = {i: [] for i in boxes}
    succs: dict[str, list[str]] = {i: [] for i in boxes}
    for a, b in edges:
        succs[a].append(b)
        preds[b].append(a)

    def pull(box: Box, neighbours: list[str]) -> list[float]:
        ns = [n for n in neighbours if n in boxes]
        if not box.dummy:
            real = [n for n in ns if not boxes[n].dummy]
            ns = real or ns
        return [boxes[n].y for n in ns]

    def separate(lane: list[Box]) -> None:
        for i in range(1, len(lane)):
            lo = lane[i - 1].y + lane[i - 1].h / 2.0 + vgap + lane[i].h / 2.0
            if lane[i].y < lo:
                lane[i].y = lo
        for i in range(len(lane) - 2, -1, -1):
            hi = lane[i + 1].y - lane[i + 1].h / 2.0 - vgap - lane[i].h / 2.0
            if lane[i].y > hi:
                lane[i].y = hi

    # Pull each box toward the mean of its neighbours, then push the rank apart
    # again. Straightens the spine and keeps a skipping edge running level.
    for p in range(passes):
        keys = sorted(ranks)
        if p % 2:
            keys.reverse()
        neigh = preds if p % 2 == 0 else succs
        for r in keys:
            lane = ranks[r]
            for b in lane:
                ys = pull(b, neigh[b.id])
                if ys:
                    b.y = (b.y + sum(ys) / len(ys)) / 2.0
            lane.sort(key=lambda b: (b.y, b.order))
            for k, b in enumerate(lane):
                b.order = k
            separate(lane)


def build(nodes: list[tuple[str, float, float]],
          edges: list[tuple[str, str, str | None, str]],
          *, hgap: float = 54.0, vgap: float = 26.0,
          pad: float = 16.0) -> Drawing:
    """*nodes* are ``(id, width, height)``; *edges* ``(src, dst, label, style)``."""
    ids = [n[0] for n in nodes]
    plain = [(a, b) for a, b, _, _ in edges]
    rank = rank_nodes(ids, plain)
    order = _initial_order(ids, plain, rank)

    boxes = {i: Box(id=i, w=w, h=h, rank=rank[i], order=order[i])
             for i, w, h in nodes}

    # one dummy per rank an edge skips
    chains: dict[tuple[str, str], list[str]] = {}
    dummy_edges: list[tuple[str, str]] = []
    for a, b, _, _ in edges:
        span = rank[b] - rank[a]
        if span <= 1:
            dummy_edges.append((a, b))
            chains[(a, b)] = []
            continue
        chain = []
        prev = a
        for r in range(rank[a] + 1, rank[b]):
            did = f"~{a}>{b}@{r}"
            boxes[did] = Box(id=did, w=0.0, h=DUMMY_H, rank=r,
                             order=order[a], dummy=True)
            dummy_edges.append((prev, did))
            chain.append(did)
            prev = did
        dummy_edges.append((prev, b))
        chains[(a, b)] = chain

    _barycentre(boxes, dummy_edges)
    _place(boxes, dummy_edges, hgap=hgap, vgap=vgap)

    routes = []
    for a, b, label, style in edges:
        pts = [(boxes[a].x + boxes[a].w, boxes[a].y)]
        pts += [(boxes[d].x, boxes[d].y) for d in chains[(a, b)]]
        pts.append((boxes[b].x, boxes[b].y))
        routes.append(Route(src=a, dst=b, points=pts, label=label, style=style))

    real = [b for b in boxes.values() if not b.dummy]
    minx = min(b.x for b in real)
    maxx = max(b.x + b.w for b in real)
    miny = min(min(b.y - b.h / 2 for b in boxes.values()),
               min(p[1] for r in routes for p in r.points))
    maxy = max(max(b.y + b.h / 2 for b in boxes.values()),
               max(p[1] for r in routes for p in r.points))

    dx, dy = pad - minx, pad - miny
    for b in boxes.values():
        b.x += dx
        b.y += dy
    for r in routes:
        r.points = [(x + dx, y + dy) for x, y in r.points]

    return Drawing(boxes=boxes, routes=routes,
                   width=round(maxx - minx + 2 * pad, 2),
                   height=round(maxy - miny + 2 * pad, 2))
