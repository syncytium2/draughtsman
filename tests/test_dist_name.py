"""The name pip is given is stated in three files and true in one place.

`pyproject.toml` declares it, `README.md` tells a reader what to type, and
`cli.py`'s no-torch hint tells them how to add torch. Nothing tied the three
together, and one of them was already wrong: the hint read
`pip install 'draughtsman[trace]'`, which installs Kyle Fuller's API Blueprint
parser rather than this. Nobody without torch had run it and read the sentence.

DECISIONS.md correction 5: a quantity with a single correct value, kept in more
than one place and allowed to disagree. This one has a sharper edge than the
Python versions do, because the failure is not a stale promise — it is a working
instruction that installs someone else's code.

`pyproject.toml` is treated as the truth because it is the only one of the three
that is executed: it is what a build and an upload actually use. The other two
are prose, and prose is what goes stale.

Modelled on `tests/test_versions.py`, deliberately: same shape, same reason.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
README = ROOT / "README.md"
CLI = ROOT / "src" / "draughtsman" / "cli.py"

# The directory under src/ that `import draughtsman` resolves to. It is NOT the
# distribution name and must not become it -- see test_the_import_name_is_not_the
# _distribution_name for why the two are allowed to differ.
IMPORT_NAME = "draughtsman"


def distribution() -> str:
    """The name pip is given. The only executed copy of this claim."""
    m = re.search(r'^name\s*=\s*"([A-Za-z0-9._-]+)"', PYPROJECT.read_text(), re.M)
    assert m, "pyproject no longer declares a distribution name"
    return m.group(1)


def test_the_cli_hint_installs_this_package_and_not_another():
    """THE ONE THIS FILE EXISTS FOR. A reader without torch is told a command;
    it ran, and it fetched an unrelated project. A wrong instruction that works
    is worse than one that errors."""
    m = re.search(r"pip install '([A-Za-z0-9._-]+)\[trace\]'", CLI.read_text())
    assert m, (
        "cli.py no longer offers a `pip install ...[trace]` hint, or has changed "
        "its shape. It is the copy of this name a reader is most likely to run.")
    assert m.group(1) == distribution(), (
        f"cli.py tells the reader to install '{m.group(1)}' but this package is "
        f"'{distribution()}'. That command runs and installs the wrong project.")


def test_the_readme_names_the_distribution():
    """A reader takes the README's word for it and never opens pyproject.toml."""
    m = re.search(r"On PyPI this is `([A-Za-z0-9._-]+)`", README.read_text())
    assert m, (
        "README no longer states the name on PyPI. It is where a reader looks, "
        "and the one copy of this claim nothing else can correct.")
    assert m.group(1) == distribution(), (
        f"README says `{m.group(1)}`; pyproject declares `{distribution()}`")


def test_the_import_name_is_not_the_distribution_name():
    """Not a typo, and not to be tidied away by a later session.

    PyPI's `draughtsman` belongs to someone else, so the distribution had to move.
    The import package did not, and should not: it is what every example, every
    docstring and the console script say. This asserts the split is intact in both
    directions, so that 'fixing' either half fails here with the reason.
    """
    assert (ROOT / "src" / IMPORT_NAME).is_dir(), (
        f"src/{IMPORT_NAME}/ is gone; the import name has moved and this test is "
        "checking nothing")
    assert distribution() != IMPORT_NAME, (
        f"the distribution name is back to '{IMPORT_NAME}', which is taken on "
        "PyPI by an unrelated project and cannot be uploaded")
    assert distribution().startswith(IMPORT_NAME), (
        f"'{distribution()}' no longer contains the import name; a reader who "
        f"installs it has no way to guess that they then `import {IMPORT_NAME}`")


def test_the_console_script_keeps_the_import_name():
    """The verb a person types is the spelling everything else uses."""
    text = PYPROJECT.read_text()
    m = re.search(r"^\[project\.scripts\]\s*\n([A-Za-z0-9._-]+)\s*=", text, re.M)
    assert m, "pyproject no longer declares a console script"
    assert m.group(1) == IMPORT_NAME, (
        f"the command is `{m.group(1)}`; every example in this repo types "
        f"`{IMPORT_NAME}`")


def test_every_file_that_makes_this_claim_is_checked_here():
    """The guard against the guard, and the first version of it could not fail.

    It listed three files and asserted they existed, which is a check that runs
    where the failure cannot be. There WAS a fourth copy at the time it was
    written -- `tests/test_ui.py` hardcoded `draughtsman[trace]` -- and this test
    passed anyway. It was found by the rename turning that file red, which is
    luck, not a check.

    So this greps the repository instead of trusting a list: every place that
    writes `<name>[trace]` must be writing the name pyproject declares.
    """
    for path in (PYPROJECT, README, CLI):
        assert path.exists(), f"{path} has moved; this test is checking nothing"

    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout.split()
    wrong = []
    for rel in tracked:
        if rel.endswith((".svg", ".json", ".png")):
            continue
        # THIS FILE IS EXEMPT AND THAT IS A REAL HOLE, NAMED RATHER THAN HIDDEN.
        # Its whole subject is the wrong name, so it has to be able to quote it;
        # it does so in the docstrings above. Nothing checks the name inside this
        # file, and a copy that lands here is a copy nobody catches. The exemption
        # is one path, so the hole is exactly one file wide.
        if rel == "tests/test_dist_name.py":
            continue
        try:
            text = (ROOT / rel).read_text()
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for m in re.finditer(r"([A-Za-z0-9._-]+)\[trace\]", text):
            # `.` is `pip install -e ".[trace]"` -- a path, not a name, and the
            # only way to install from a clone. An f-string that derives the name
            # is the correct way to write the name itself.
            if m.group(1) in {"distribution()", "name", "."}:
                continue
            if m.group(1) != distribution():
                wrong.append((rel, m.group(1)))
    assert not wrong, (
        f"files name a package other than {distribution()!r} in an install "
        f"instruction: {wrong}. Derive it from pyproject rather than typing it.")
