import json
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
