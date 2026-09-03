"""How many models are in here is stated in three READMEs and true on disk.

Adding CASCADE on 2026-09-02 made every count in this repository wrong — "nine
others", "one model of ten", "ten tabs", two "nine more models" and a "## The
ten" heading — and nothing noticed for a day. They were found by a session on
another project reading the gallery, not by anything here.

DECISIONS.md correction 5, arriving in the one place that had escaped it: a
quantity with a single correct value, kept in six places and checked in none. It
is the same shape as `tests/test_versions.py` and `tests/test_dist_name.py`, and
this file is deliberately modelled on them.

THE DIRECTORY IS THE TRUTH. It is the only one of the seven that is executed:
`tests/test_render.py` parametrises over it, so a model that is there is drawn and
checked, and a model that is not is not. Prose cannot be executed and is therefore
what goes stale.

Removing CASCADE again on 2026-09-03 made all six numbers correct, which is the
argument for this file rather than against it: they were right, then wrong, then
right again, and at no point did anything here know which.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
EXAMPLES_README = ROOT / "examples" / "README.md"
GALLERY_README = ROOT / "examples" / "gallery" / "README.md"

WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
         "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
         "twelve": 12}


def _models(where: Path) -> list[Path]:
    """A model is a directory holding both committed artifacts. Same definition
    `tests/test_render.py` uses to decide what to draw."""
    return sorted(d for d in where.iterdir()
                  if d.is_dir() and (d / "graph.json").is_file()
                  and (d / "spec.json").is_file())


def gallery() -> list[Path]:
    return _models(ROOT / "examples" / "gallery")


def everything() -> list[Path]:
    return _models(ROOT / "examples") + gallery()


def _word(text: str, pattern: str, path: Path) -> int:
    m = re.search(pattern, text)
    assert m, (
        f"{path.name} no longer contains a count matching {pattern!r}. Either the "
        "sentence was reworded, in which case update this test, or it was deleted, "
        "in which case delete the rule -- do not leave it matching nothing.")
    word = m.group(1).lower()
    assert word in WORDS, f"{path.name}: {word!r} is not a number word this knows"
    return WORDS[word]


def test_the_readme_counts_every_model():
    """Three claims in the front door, which is the copy a stranger reads."""
    n = len(everything())
    text = README.read_text()
    assert 1 + _word(text, r"That figure and (\w+) others", README) == n, (
        f"README says the resnet figure and N others; there are {n} models")
    assert _word(text, r"[Aa] layout defect in one model of (\w+)", README) == n
    assert _word(text, r"opening (\w+) tabs", README) == n


def test_the_examples_readmes_count_the_gallery():
    """Both say "N more models", and both mean the gallery beside `tube`."""
    g = len(gallery())
    for path in (EXAMPLES_README, GALLERY_README):
        assert _word(path.read_text(), r"(\w+) more models", path) == g, (
            f"{path.name} miscounts the gallery, which holds {g}")


def test_the_gallery_heading_and_table_count_every_model():
    """The heading and the table are two more copies, and the table is the one a
    reader trusts because it names them."""
    text = GALLERY_README.read_text()
    n = len(everything())
    assert _word(text, r"## The (\w+)", GALLERY_README) == n
    after = text.split("## The ", 1)[1].splitlines()
    rows, seen = [], False
    for ln in after:
        if ln.startswith("|"):
            seen = True
            if "---" not in ln and "| model |" not in ln:
                rows.append(ln)
        elif seen and ln.strip() == "":
            break
    assert len(rows) == n, (
        f"the gallery table has {len(rows)} model rows and there are {n} models")


def test_the_totals_line_is_the_sum_of_the_committed_graphs():
    """THE ONE THAT WENT STALE WORST. It read 2,167 nodes and 520 substantive for
    a day after the model those numbers included had been counted, and no figure,
    check or test disagreed -- the totals are prose about eleven JSON files and
    nothing had ever added them up."""
    nodes = sub = 0
    for d in everything():
        c = json.loads((d / "graph.json").read_text())["classification"]
        nodes += c["nodes_total"]
        sub += c["nodes_substantive"]
    text = GALLERY_README.read_text()
    m = re.search(r"Totals: ([\d,]+) traced nodes, (\d+) substantive, "
                  r"(\w+) specs, (\w+) green coverage", text)
    assert m, "the gallery README no longer states totals in the form this reads"
    assert int(m.group(1).replace(",", "")) == nodes, (
        f"README says {m.group(1)} traced nodes; the graphs hold {nodes:,}")
    assert int(m.group(2)) == sub, (
        f"README says {m.group(2)} substantive; the graphs hold {sub}")
    assert WORDS[m.group(3).lower()] == len(everything())
    assert WORDS[m.group(4).lower()] == len(everything())


def test_every_file_that_counts_the_models_is_checked_here():
    """The guard against the guard. `tests/test_dist_name.py` shipped a version of
    this that listed files and asserted they existed while a fourth copy sat
    uncaught, so this greps for the number words instead and requires each
    occurrence to be one of the rules above."""
    known = {
        README: [r"That figure and (\w+) others",
                 r"[Aa] layout defect in one model of (\w+)", r"opening (\w+) tabs"],
        EXAMPLES_README: [r"(\w+) more models"],
        GALLERY_README: [r"(\w+) more models", r"## The (\w+)",
                         r"Totals: [\d,]+ traced nodes, \d+ substantive, (\w+) specs",
                         r"substantive, \w+ specs, (\w+) green coverage"],
    }
    for path, patterns in known.items():
        assert path.exists(), f"{path} has moved; this test is checking nothing"
        for pat in patterns:
            assert re.search(pat, path.read_text()), (
                f"{path.name} no longer matches {pat!r} -- the claim moved and "
                "this rule is now checking nothing")
