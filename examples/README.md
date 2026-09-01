# The five failures, kept as the regression suite

These are not decoration. They are what five existing tools produced for the same
1,149-parameter model, and they are the bar `draughtsman` has to clear. See
[`../SPEC.md`](../SPEC.md) §2 for versions and measurements.

| file | tool | verdict |
|---|---|---|
| `1-current-hand-laid.png` | bugarach's own generator | The only one that got the topology right. Content derived from the model; **coordinates placed by hand**, which is why this repo exists. |
| `2-torchview-traced.png` | torchview 0.2.7 | Correct and unusable — ~40 nodes, a strip one pixel tall at page width. |
| `4-pytorchgraph-paper.png` | pytorch-graph 0.2.5 | **The instructive one.** Clean, styled, and it silently omitted the pooling, the mean, all four DoG kernels, the bypass and the concat. Empty shape fields. A reader would come away confident and wrong. |

**Acceptance test:** the figure shows the fan-out to four kernels, the bypass, and
the concat. Every tool above except the first failed that.

## What draughtsman draws for the same model

[`tube/figure.svg`](tube/figure.svg), with the `graph.json` and `spec.json` it came
from and a note on where every number in it originates — see
[`tube/README.md`](tube/README.md). It clears the bar: the fan-out is four lanes,
the bypass is a dashed arc around them, the concat is a stage of its own, and the
twenty-six kernel-construction operations that made torchview a strip collapse
into one named block. The topology is the hand-laid figure's; the coordinates are
not placed by anyone.

## The generalisation run

[`gallery/`](gallery/) — nine more models across five architecture families, each
chosen for a specific way it could break the tool, with the two things that did
break it and the four gaps still open. Read
[`gallery/README.md`](gallery/README.md) before trusting the design to generalise
from `tube` alone.
