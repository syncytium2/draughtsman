import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

EXAMPLE = ROOT / "examples" / "tube"


@pytest.fixture(scope="session")
def tube_graph():
    from draughtsman.facts import Graph
    return Graph(json.loads((EXAMPLE / "graph.json").read_text()))


@pytest.fixture(scope="session")
def tube_spec():
    from draughtsman.spec import load
    return load(json.loads((EXAMPLE / "spec.json").read_text()))


@pytest.fixture(scope="session")
def example_dir():
    return EXAMPLE


def all_examples():
    """Every committed model: `examples/tube` plus the gallery. Used to
    parametrise the checks, so a tenth model is covered by adding a folder."""
    return sorted((p.parent for p in (ROOT / "examples").glob("*/graph.json")),
                  key=lambda p: p.name) + \
        sorted((p.parent for p in (ROOT / "examples").glob("*/*/graph.json")),
               key=lambda p: p.name)


EXAMPLES = all_examples()
IDS = [p.name for p in EXAMPLES]


# --------------------------------------------------------------------------------
# A skip is what silence looks like when it is being careful.
#
# This suite is arranged so that nothing needs to skip: `render` and `check` want
# neither torch nor a system binary, and the one module that does want torch has
# it in the dev extra. That arrangement is easy to lose — one `pytest.mark.skipif`
# added in a hurry and a whole area stops being tested without saying so. With
# DRAUGHTSMAN_NO_SKIPS=1, which CI sets, a skip fails the run and names itself.

_SKIPPED: list[str] = []


def pytest_runtest_logreport(report):
    if report.skipped:
        _SKIPPED.append(report.nodeid)


def pytest_sessionfinish(session, exitstatus):
    if not _SKIPPED or os.environ.get("DRAUGHTSMAN_NO_SKIPS") != "1":
        return
    session.exitstatus = 1
    print("\nDRAUGHTSMAN_NO_SKIPS is set and these tests skipped:")
    for nodeid in _SKIPPED:
        print(f"  {nodeid}")
    print("Give the test what it needs, or delete it. Do not let it go quiet.")
