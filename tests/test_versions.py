"""Which Pythons this supports is asserted in three files and true in one place.

`pyproject.toml` states a floor, the CI matrix states the set actually run, and
`README.md` tells a reader what to expect. Nothing tied them together, so today
they agree by luck and tomorrow one of them moves.

DECISIONS.md correction 5: a quantity with a single correct value, kept in more
than one place and allowed to disagree. The version this repository supports is
exactly that, and it is the kind that goes wrong quietly — a floor that no longer
matches the matrix is a promise nobody is testing, and a README that names a
version CI dropped is a promise nobody is keeping.

The matrix is treated as the truth because it is the only one of the three that
is executed. The other two must agree with it.

Parsed with regular expressions rather than `tomllib`, which is 3.11 and up: a
test of the 3.10 floor that cannot run on 3.10 would be its own instance of this.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
README = ROOT / "README.md"


def _key(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split("."))


def ci_versions() -> list[str]:
    """The set CI actually runs, which is the only executed claim of the three."""
    line = re.search(r"^\s*python:\s*\[(.+?)\]\s*$", WORKFLOW.read_text(),
                     re.M)
    assert line, "the workflow no longer declares a python matrix"
    found = re.findall(r'"([\d.]+)"', line.group(1))
    assert found, "the python matrix is empty"
    return sorted(found, key=_key)


def requires_python() -> str:
    m = re.search(r'^requires-python\s*=\s*">=([\d.]+)"', PYPROJECT.read_text(),
                  re.M)
    assert m, "pyproject no longer states a requires-python floor"
    return m.group(1)


def test_the_declared_floor_is_the_lowest_version_ci_runs():
    """A floor below the matrix is a promise nobody tests; a floor above it means
    CI is running a version the package says it does not support."""
    versions = ci_versions()
    assert requires_python() == versions[0], (
        f"pyproject says >={requires_python()} but CI's lowest is {versions[0]}. "
        "Either run the version you promise, or promise the version you run."
    )


def test_the_matrix_is_contiguous():
    """A gap in the matrix means a version between the floor and the ceiling is
    promised and never run — the same hole, harder to see."""
    versions = ci_versions()
    majors = {v.split(".")[0] for v in versions}
    assert majors == {"3"}, f"a non-3.x version appeared: {versions}"
    minors = sorted(int(v.split(".")[1]) for v in versions)
    assert minors == list(range(minors[0], minors[-1] + 1)), (
        f"CI skips a version inside its own range: {versions}")


def test_the_readme_names_the_versions_ci_runs():
    """A reader takes the README's word for it and never sees the matrix."""
    versions = ci_versions()
    text = README.read_text()
    stated = re.search(r"Python ([\d.]+) through ([\d.]+)", text)
    assert stated, (
        "README no longer states a supported range. It is where a reader looks, "
        "and it is the copy of this claim that nothing else can correct.")
    assert [stated.group(1), stated.group(2)] == [versions[0], versions[-1]], (
        f"README says Python {stated.group(1)} through {stated.group(2)}; "
        f"CI runs {', '.join(versions)}")


def test_every_file_that_makes_this_claim_is_checked_here():
    """The guard against the guard: if a fourth place starts claiming a version,
    this file is the reason nobody notices. Named so the list is visible."""
    claimants = {PYPROJECT, WORKFLOW, README}
    for path in claimants:
        assert path.exists(), f"{path} has moved; this test is checking nothing"
