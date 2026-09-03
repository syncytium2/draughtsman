# Contributing

This repository is two things at once: a tool that draws architecture figures,
and a record of how it was built by Claude Code sessions working concurrently.
Both are open to contribution, and the second is the unusual one — most of what
is written down here is about *how* rather than *what*, because that is where the
time went.

## The one rule that matters

**One quantity, one implementation, and something that fails when it cannot be
answered.**

That is [`DECISIONS.md`](https://github.com/syncytium2/draughtsman/blob/main/DECISIONS.md)
correction 5, and nine corrections there are the same shape: a value with one
correct answer was computed in two places and allowed to disagree, or computed in
one place and never checked — and in every case the tests were green while the
figure was wrong. If you find yourself typing a number that is derivable, derive
it. If you keep a fact in two files, add the assertion that ties them.

The corrections are worth reading before you change anything, because most of
them were found the expensive way.

## What a change looks like here

- **Commit messages carry the reasoning.** They are long on purpose. The finding,
  the measurement, and what was tried and rejected go in the message rather than
  in a comment or a scratchpad, because the message is the only artifact that
  survives every session.
- **Comments say why, not what.** The code is readable; the reason a constant is
  `4.0` and not `3.0` is not.
- **A new number needs an argument.** `SHEET_MIN_PITCH` exists because sheets a
  reader cannot separate are not a count. `MARK_MAX` is 32 because counting stops
  working around thirty. Both are in the source with the measurement attached.
- **If a check cannot fail, it is not a check.** Several tests here carry a
  vacuity guard — an assertion that the test found something to examine — because
  two of them were caught passing while checking nothing.

## Running it

```
pip install -e ".[dev]"      # pytest, and torch for the tracer
pytest                       # the whole suite
```

`trace` needs torch. `render` and `check` do not, and that is deliberate: layout
is written here rather than delegated to graphviz, so a machine that only draws a
figure needs no heavy dependency and no system binary. Keep it that way.

CI runs on **every branch**, not just `main`, because a filter of `[main]` makes
the gate a post-mortem — see
[`DECISIONS.md`](https://github.com/syncytium2/draughtsman/blob/main/DECISIONS.md)
correction 8, where a check ran somewhere it could not see and reported the thing
it was checking as broken.

## If you are a Claude Code session

[`CLAIMS.md`](https://github.com/syncytium2/draughtsman/blob/main/CLAIMS.md) is
the board, and it is checked by
[`tests/test_claims.py`](https://github.com/syncytium2/draughtsman/blob/main/tests/test_claims.py)
rather than trusted. Its seven rules were each written after a near-miss, and the
file says which. Work in a worktree, claim the paths before you write, and
release the claim in the commit **before** you land.

Rule 7 is the one nothing can check: a session that does not appear on the board
is not accounted for. It has already happened.

## Figures

If you change the renderer, the committed figures in
[`examples/`](https://github.com/syncytium2/draughtsman/blob/main/examples/) are
re-rendered in the same commit. They are not illustrations — they are the
regression suite, and several defects in this repository were found by looking at
one rather than by running anything.

Never ship a figure with overlapping text. That rule is borrowed from a sibling
project and it is absolute; the assertion that enforces it here is
`test_no_stage_name_is_painted_over_its_own_glyph`.

## Licence

BSD-3-Clause. By contributing you agree your work is licensed the same way.
