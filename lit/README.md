# lit — the papers behind the models

Sources for gallery models that come from published work rather than from a
sketch written to break the tool. A figure of somebody else's architecture is a
claim about their paper, and the paper has to be on disk for anyone to check it.

## The PDFs are not in git, and that is deliberate

**Nothing in `lit/` that is a PDF is committed.** This repository is public, it is
BSD-3, and it carries a DOI. A 1986 Springer paper is not ours to redistribute and
no licence here covers it. `.gitignore` keeps them out.

This is the CASCADE question arriving a second time — a licence problem entering
through a file somebody added because it was useful — and the answer is decided
before anything lands rather than after. See `CLAIMS.md` queue item 0: CASCADE was
GPL-3.0 against this repo's BSD-3, and moving it out was cheaper than the argument
would have been.

What IS committed: this file, `_NEEDED.md`, and any notes taken from a paper. A
note in your own words about what a model does is yours to license. A scan is not.

## Getting a paper

The estate's tool is `murderboard/fetch_paper.py`. It is not vendored here —
one implementation, called with an environment variable, which is the same rule
`tools/estate.py` states about the five copies of the git wrapper it replaced.

```
export MURDERBOARD_LIT="$(git rev-parse --show-toplevel)/lit"
cd ~/Developer/murderboard

python3 fetch_paper.py --have malsburg cocktail    # ALWAYS first: is it already here?
python3 fetch_paper.py <url>                       # open-access hosts only
python3 fetch_paper.py --need "Author, Title, Journal vol:pp (year)" \
                       --url <url> --reason "paywalled"
```

`--have` before `--need` before a download, in that order. The tool restricts
itself to open-access hosts by design: it will not scrape ScienceDirect, Nature or
Wiley, and it is not a general downloader. When a paper is behind a publisher, the
honest move is `--need`, which appends a line to `_NEEDED.md` for a person to
clear. That file is the record of what the repository wants and cannot reach.

## Index

| paper | for | held |
|---|---|---|
| von der Malsburg & Schneider 1986, *A neural cocktail-party processor*, Biological Cybernetics 54:29–40 | a candidate gallery model: a dynamical net whose output is a synchrony pattern rather than a tensor | **held** — see [`malsburg-1986.md`](malsburg-1986.md) for the model and what it costs to draw |
| von der Malsburg 1981, *The Correlation Theory of Brain Function* | the theory the 1986 model applies; author-deposited and reachable | see [`malsburg-1986.md`](malsburg-1986.md) |

## Why this one, and what it is expected to break

Every model in `examples/gallery/` is a function from a tensor to a tensor, and
draughtsman's three stages assume exactly that: trace a computation graph, group
its nodes, look the quantities back up. The cocktail-party processor is not that
shape.

- **The output is a correlation, not a tensor.** What the network computes is
  which units are firing in synchrony — that is the segregated stream. A
  correlation between two units' activity is not an edge in a computation graph,
  and `check` refuses any drawn edge no node consumes. The relation the figure
  most needs to show does not exist in the trace.
- **The parameters carry nothing.** `params` is the quantity every figure here
  reads back. This is a coupling topology plus a dynamics; most stages would
  render `0 params`.
- **Time unrolls into a ribbon.** Tracing T steps of an oscillator loop yields T
  copies of one update — correct and unreadable, which is the torchview failure
  `README.md` convicts, arriving from the opposite direction.

The gallery's one recurrent model, `lstm`, hides its recurrence inside a fused
cuDNN op and says so in its own caption. **So this would be the first model here
whose recurrence actually reaches the trace.**

The useful outcome may be a refusal rather than a figure. That is a finding, and
it is the kind this repository is for.
