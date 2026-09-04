#!/usr/bin/env python3
"""How far does the agent's grouping move between independent runs?

    tools/abstract_variance.py experiments/abstraction-variance/run-*.json
    tools/abstract_variance.py --selftest

WHY THIS EXISTS. Every other claim this repository makes is checked: the agent
supplies no facts, coverage, arrows against the trace, repetition counts,
reference resolution, glyph axes, type size at print width. About the QUALITY OF
THE ABSTRACTION -- the one step the tool is named for -- nothing. "How do you
know the agent is any good at this?" answered to "a person looked at the
figures", in a repository whose argument is that an unchecked claim is
decoration.

WHAT IS MEASURED, AND WHY IT IS THE ADJUSTED RAND INDEX. The obvious comparisons
are all wrong. Stage COUNT is not agreement: two runs can both produce nine
stages and cut the model in completely different places. Stage NAMES are not
agreement either: "stem" and "input convolution" are the same judgement in
different words, and a string comparison would score that as total disagreement
while scoring a genuine disagreement that happened to reuse a word as partial
credit.

The question is whether two runs put the SAME OPERATIONS TOGETHER. That is a
partition-comparison problem, and the adjusted Rand index is its standard answer:
it counts the pairs of nodes the two runs agree about -- together in both, or
apart in both -- and then subtracts the agreement two random partitions of those
sizes would reach anyway. So it is invariant to how many stages there are and to
what they are called, which is exactly the invariance this measurement needs.

    1.0   identical partitions
    0.0   no better than chance for partitions of these sizes
    < 0   worse than chance

CHANCE IS THE POINT OF THE ADJUSTMENT. An unadjusted Rand index on a 52-node
graph cut into nine parts scores about 0.85 for two partitions that share
nothing, because most pairs of nodes are in different stages under any grouping
and every one of those counts as agreement. A raw score would therefore report
this design as working no matter what came back.

ELISION IS A DECISION, NOT A GAP. A node a run elided is not missing from that
run's partition -- the run said "this belongs nowhere, and here is why". So
elided nodes go into one cluster of their own, and two runs that elide the same
node agree about it.
"""

from __future__ import annotations

import glob
import json
import sys
from itertools import combinations
from pathlib import Path

ELIDED = "__elided__"


def partition(spec: dict) -> dict[str, str]:
    """node id -> the label of the group it was put in.

    The label is the stage's INDEX, not its name. Two runs that make the same cut
    and name it differently must score as agreeing, and a name is not evidence.
    """
    out: dict[str, str] = {}
    for i, stage in enumerate(spec.get("stages", [])):
        for n in stage.get("nodes", []):
            out[n] = f"s{i}"
    for e in spec.get("elided", []):
        for n in (e.get("nodes", []) if isinstance(e, dict) else [e]):
            out[n] = ELIDED
    return out


def _pairs(n: int) -> int:
    return n * (n - 1) // 2


def adjusted_rand(a: dict[str, str], b: dict[str, str]) -> float | None:
    """ARI over the nodes both runs placed. None if they share fewer than two."""
    shared = sorted(set(a) & set(b))
    if len(shared) < 2:
        return None
    table: dict[tuple[str, str], int] = {}
    rows: dict[str, int] = {}
    cols: dict[str, int] = {}
    for n in shared:
        ka, kb = a[n], b[n]
        table[(ka, kb)] = table.get((ka, kb), 0) + 1
        rows[ka] = rows.get(ka, 0) + 1
        cols[kb] = cols.get(kb, 0) + 1
    n_pairs = _pairs(len(shared))
    if n_pairs == 0:
        return None
    index = sum(_pairs(v) for v in table.values())
    ra = sum(_pairs(v) for v in rows.values())
    cb = sum(_pairs(v) for v in cols.values())
    expected = ra * cb / n_pairs
    maximum = 0.5 * (ra + cb)
    if maximum == expected:
        # Both runs put everything in one group, or every node in its own. The
        # partitions are identical and the index is undefined rather than zero;
        # saying 1.0 here is the honest reading and saying 0.0 would be a lie.
        return 1.0
    return (index - expected) / (maximum - expected)


def report(paths: list[str]) -> int:
    runs = []
    for p in paths:
        spec = json.loads(Path(p).read_text())
        runs.append((Path(p).stem, spec, partition(spec)))
    if len(runs) < 2:
        print("need at least two runs to compare", file=sys.stderr)
        return 2

    print(f"{len(runs)} runs\n")
    print(f"  {'run':<10} {'stages':>7} {'placed':>7} {'elided':>7} {'edges':>6}")
    for name, spec, part in runs:
        el = sum(1 for v in part.values() if v == ELIDED)
        print(f"  {name:<10} {len(spec.get('stages', [])):>7} "
              f"{len(part) - el:>7} {el:>7} {len(spec.get('edges', [])):>6}")

    counts = [len(s.get("stages", [])) for _, s, _ in runs]
    print(f"\n  stage count: min {min(counts)}, max {max(counts)}, "
          f"spread {max(counts) - min(counts)}")

    print("\nADJUSTED RAND INDEX — do two runs put the same operations together?")
    print("  1.0 identical · 0.0 no better than chance for partitions this size\n")
    scores = []
    for (na, _, pa), (nb, _, pb) in combinations(runs, 2):
        ari = adjusted_rand(pa, pb)
        if ari is None:
            print(f"  {na} vs {nb}: too few shared nodes")
            continue
        scores.append(ari)
        print(f"  {na} vs {nb}: {ari:.3f}")
    if scores:
        mean = sum(scores) / len(scores)
        print(f"\n  mean {mean:.3f}   min {min(scores):.3f}   max {max(scores):.3f}")

    # A node every run placed the same way is a judgement the design can rely on;
    # one that moves in every run is where the abstraction is actually undecided.
    everywhere = set.intersection(*[set(p) for _, _, p in runs])
    unanimous = sum(1 for n in everywhere
                    if len({p[n] for _, _, p in runs}) == 1)
    print(f"\n  nodes every run placed: {len(everywhere)}")
    print(f"  of those, put with exactly the same companions by every run: "
          f"{unanimous}")
    return 0


def selftest() -> int:
    """The measure must fail where it should, or it cannot report a null result.

    Three cases, and the third is the one that matters: an index that cannot tell
    a real grouping from a random one would score this whole experiment as a
    success no matter what came back.
    """
    a = {"n1": "s0", "n2": "s0", "n3": "s1", "n4": "s1"}
    same = adjusted_rand(a, a)
    assert same is not None and abs(same - 1.0) < 1e-9, f"identical scored {same}"

    renamed = {"n1": "sX", "n2": "sX", "n3": "sY", "n4": "sY"}
    r = adjusted_rand(a, renamed)
    assert r is not None and abs(r - 1.0) < 1e-9, (
        f"the same cut with different labels scored {r}; the measure is reading "
        "names, which is exactly what it must not do")

    # A partition that agrees about no pair scores BELOW zero, not at it: it has
    # done worse than two random partitions of these sizes would. An unadjusted
    # Rand index scores this same case at 0.33 and reads as partial agreement.
    crossed = {"n1": "s0", "n2": "s1", "n3": "s0", "n4": "s1"}
    c = adjusted_rand(a, crossed)
    assert c is not None and abs(c - (-0.5)) < 1e-9, (
        f"a partition sharing no pair scored {c}, expected -0.5")

    # Every node in its own stage is the degenerate answer, and it lands on
    # EXACTLY chance. This is the case that matters most: a measure that gave it
    # credit would let a run that grouped nothing report as partial success.
    split = {"n1": "s0", "n2": "s1", "n3": "s2", "n4": "s3"}
    s = adjusted_rand(a, split)
    assert s is not None and abs(s) < 1e-9, (
        f"every-node-alone scored {s}, expected exactly 0.0 — chance")

    assert partition({"stages": [{"nodes": ["a", "b"]}],
                      "elided": [{"nodes": ["c"]}]}) == {
        "a": "s0", "b": "s0", "c": ELIDED}, "elision is not being read"

    print("selftest OK — identical 1.0, renamed 1.0, no-pair-shared -0.5, "
          "every-node-alone exactly 0.0 (chance), elision read")
    return 0


def main(argv: list[str]) -> int:
    args = argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if args[0] == "--selftest":
        return selftest()
    paths: list[str] = []
    for a in args:
        paths.extend(sorted(glob.glob(a)) if any(c in a for c in "*?[") else [a])
    return report(paths)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
