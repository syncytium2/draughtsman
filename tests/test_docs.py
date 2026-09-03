"""Every flag the documentation shows a reader typing must exist.

`SPEC.md` §7 documented `draughtsman abstract --dry-run` from the day it was
written. There has never been such a flag. It survived every test in this suite,
CI on four Pythons, and a reader following the document would have got
`error: unrecognized arguments`.

It is the same shape as `tests/test_versions.py`, `tests/test_dist_name.py` and
`tests/test_counts.py`: a claim about the tool, kept in prose, checked by nothing.
Prose cannot be executed, so prose is what goes stale — and an instruction is the
worst kind, because a reader runs it.

SCOPE, chosen so this cannot cry wolf. Only flags on a line that invokes
`draughtsman` are checked. The documentation also shows `pip`, `git` and `gh`
commands, and their flags are not ours to verify; a guard that flagged those would
be turned off, which is the reasoning `check` already applies to its own warnings.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "src" / "draughtsman" / "cli.py"


def defined_flags() -> set[str]:
    """The long options the CLI actually declares. Derived, never recalled."""
    return set(re.findall(r'"(--[a-z][a-z-]*)"', CLI.read_text()))


def _command_lines() -> list[tuple[str, str]]:
    """Every line inside a fenced code block that invokes `draughtsman`.

    SCOPED TO CODE BLOCKS, and the first version was not. It read any line
    containing "draughtsman ", which in this repository's prose means sentences —
    "draughtsman draws", "draughtsman puts an agent in that step" — and it duly
    reported `draws` and `puts` as undefined subcommands. A guard that reports
    English as a defect is one nobody keeps, so the scope is the fence: a command
    is something shown to be typed.
    """
    out = []
    tracked = subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.split()
    for rel in tracked:
        fenced = False
        for line in (ROOT / rel).read_text().splitlines():
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if fenced and "draughtsman " in line:
                out.append((rel, line))
    return out


def documented_flags() -> dict[str, list[str]]:
    """Long options shown in a `draughtsman` command, by file."""
    out: dict[str, list[str]] = {}
    for rel, line in _command_lines():
        for flag in re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", line):
            out.setdefault(flag, []).append(rel)
    return out


def test_every_documented_flag_exists():
    """THE ONE THIS FILE EXISTS FOR. A documented flag that does not exist is an
    instruction that fails for the reader who follows it."""
    defined = defined_flags()
    assert defined, "no long options found in cli.py — this test is checking nothing"
    missing = {f: sorted(set(w)) for f, w in documented_flags().items()
               if f not in defined}
    assert not missing, (
        "documentation shows flags the CLI does not define: "
        + "; ".join(f"{f} in {', '.join(w)}" for f, w in sorted(missing.items()))
        + ". Either add the flag or fix the document — a reader will type it.")


def test_the_documentation_shows_the_verbs_that_exist():
    """A verb is a stronger claim than a flag and drifts the same way."""
    text = CLI.read_text()
    verbs = set(re.findall(r'sub\.add_parser\(\s*"([a-z]+)"', text))
    assert verbs, "no subcommands found in cli.py — this test is checking nothing"
    shown = set()
    for _rel, line in _command_lines():
        m = re.search(r"draughtsman\s+([a-z]+)", line)
        if m:
            shown.add(m.group(1))
    invented = shown - verbs
    assert not invented, (
        f"documentation shows subcommands the CLI does not define: {sorted(invented)}")


def test_this_guard_can_see_a_flag_that_is_not_there():
    """The guard against the guard. `documented_flags` reads only lines containing
    `draughtsman `, so a scope narrowed by accident would silently check nothing.
    This asserts the scan still reaches real content."""
    found = documented_flags()
    assert found, (
        "no draughtsman invocations with flags were found in any tracked markdown. "
        "Either the documentation stopped showing commands, or this scan's scope "
        "narrowed and it is now checking nothing.")
