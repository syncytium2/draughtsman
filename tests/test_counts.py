"""The models are NAMED, not counted, and the names are checked against the disk.

WHY NAMING RATHER THAN COUNTING. Adding one model on 2026-09-02 falsified six
sentences at once — "nine others", "one model of ten", "ten tabs", two "nine more
models" and a "## The ten" heading — plus a totals line and a `>= 10` floor in
`tests/test_reproduces.py`. Seven claims, one addition, and only the executed one
failed. A count is a claim about a set that does not name the set, so nothing it
says can be checked against anything except by hand, which is the arrangement
DECISIONS.md correction 5 is entirely about.

A list is different in kind. `examples/gallery/README.md` names every model, and a
name can be compared with a directory. So the table is now the claim, this file
compares it against the disk in BOTH directions, and the prose says "every model"
where it used to say a number.

THE DIRECTORY IS THE TRUTH, because it is the only copy that is executed:
`tests/test_render.py` draws what is there and `tests/test_reproduces.py`
re-traces it. Prose cannot be executed and is therefore what goes stale.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
EXAMPLES_README = ROOT / "examples" / "README.md"
GALLERY_README = ROOT / "examples" / "gallery" / "README.md"

# This file quotes the number words it forbids, so it cannot check itself. The
# exemption is one path wide and is named here rather than left implicit.
SELF = "tests/test_counts.py"


def _models(where: Path) -> set[str]:
    """A model is a directory holding both committed artifacts -- the same
    definition `tests/test_render.py` uses to decide what to draw."""
    return {d.name for d in where.iterdir()
            if d.is_dir() and (d / "graph.json").is_file()
            and (d / "spec.json").is_file()}


def on_disk() -> set[str]:
    return _models(ROOT / "examples") | _models(ROOT / "examples" / "gallery")


def in_the_table() -> set[str]:
    """Every model the gallery table names, by the directory it links to."""
    names = set()
    for line in GALLERY_README.read_text().splitlines():
        m = re.match(r"\|\s*\[`([^`]+)`\]\(([^)]+)\)\s*\|", line)
        if m:
            names.add(m.group(2).strip("/").split("/")[-1])
    return names


def test_the_table_names_every_model_that_is_on_disk():
    """A model added and not listed is a model no reader knows about."""
    missing = on_disk() - in_the_table()
    assert not missing, (
        f"models are on disk and absent from the gallery table: {sorted(missing)}. "
        "The table is the list a reader trusts; add the row.")


def test_the_table_names_nothing_that_is_not_on_disk():
    """The other direction, and the one that actually went wrong: CASCADE sat in
    this table after its directory was removed would be a link to nothing."""
    phantom = in_the_table() - on_disk()
    assert not phantom, (
        f"the gallery table names models that are not on disk: {sorted(phantom)}. "
        "Either the directory was removed and the row should have gone with it, "
        "or the link is wrong.")


def test_the_totals_line_is_the_sum_of_the_committed_graphs():
    """The one aggregate worth stating, and the only number left in this prose.

    It read 2,167 nodes and 520 substantive for a day after the model those
    numbers included had been counted, and nothing disagreed -- the totals are
    prose about a directory of JSON files and nothing had ever added them up.
    """
    nodes = sub = 0
    for name in sorted(on_disk()):
        for base in (ROOT / "examples", ROOT / "examples" / "gallery"):
            d = base / name
            if (d / "graph.json").is_file():
                c = json.loads((d / "graph.json").read_text())["classification"]
                nodes += c["nodes_total"]
                sub += c["nodes_substantive"]
                break
    m = re.search(r"Totals: ([\d,]+) traced nodes, (\d+) substantive",
                  GALLERY_README.read_text())
    assert m, "the gallery README no longer states totals in the form this reads"
    assert int(m.group(1).replace(",", "")) == nodes, (
        f"README says {m.group(1)} traced nodes; the graphs hold {nodes:,}")
    assert int(m.group(2)) == sub, (
        f"README says {m.group(2)} substantive; the graphs hold {sub}")


def test_no_readme_counts_the_models_in_prose():
    """THE POLICY, ENFORCED RATHER THAN REMEMBERED.

    Removing the six counts fixes today. This is what stops the seventh being
    written next week by someone who does not know why the sentence says "every
    model" instead of a number. A count of models in prose is a claim that cannot
    be compared with anything, so it is refused here and the writer is pointed at
    the table.

    Deliberately narrow: it catches number words attached to the nouns that mean
    models, not every number in the documentation. `2,078 traced nodes` is a
    checked aggregate and stays; "Two of them broke it" is a finding about a run
    and is not a claim about what the directory holds.
    """
    words = ("one", "two", "three", "four", "five", "six", "seven", "eight",
             "nine", "ten", "eleven", "twelve")
    # "families" is deliberately NOT here. It carries two senses in this
    # repository and neither is a claim about the directory: README's "two
    # families" is the two families of tool failure, and the gallery's "three
    # families" counts the rows of the table printed directly beneath it. A guard
    # that flagged those would be crying wolf, and a guard that cries wolf is
    # turned off -- which is the reasoning `check` already applies to warnings.
    nouns = ("models", "others", "specs", "tabs", "figures", "coverage checks")
    pattern = re.compile(
        r"\b(" + "|".join(words) + r")\b[ \-]*(?:more |committed |worked )?\b("
        + "|".join(nouns) + r")\b", re.I)
    offenders = []
    for path in (README, EXAMPLES_README, GALLERY_README):
        for i, line in enumerate(path.read_text().splitlines(), 1):
            for m in pattern.finditer(line):
                offenders.append(f"{path.relative_to(ROOT)}:{i}: {m.group(0)!r}")
    assert not offenders, (
        "the documentation counts models in prose again:\n  "
        + "\n  ".join(offenders)
        + "\nName them instead. The gallery table is the list, and "
          "tests/test_counts.py checks it against the directories.")


def test_this_files_own_exemption_is_still_only_one_file():
    """The guard against the guard. An earlier version of this idea listed files
    and asserted they existed while a fourth copy of the claim sat uncaught, so
    the exemption is stated as a path and checked to be that path."""
    assert (ROOT / SELF).is_file(), f"{SELF} has moved; the exemption is stale"
    assert SELF not in {str(README), str(EXAMPLES_README), str(GALLERY_README)}
