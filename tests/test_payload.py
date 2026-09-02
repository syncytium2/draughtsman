"""The stage-2 payload must describe the spec format it is asking for.

SPEC.md §8.1 decided that `abstract` prints a prompt and an agent answers it. That
makes this text the ENTIRE interface to stage 2 — an agent knows exactly what it
says and nothing else. When it goes stale the failure is silent and expensive:
`layout` shipped, no spec written afterwards used it, and every figure in the
gallery came out an 8:1 ribbon because the thing writing them had never been told
wrapping existed.

Nothing was broken. Every check was green. The tool simply could not be asked for
the thing it could do.
"""

import dataclasses
import json

import pytest

from draughtsman import spec as spec_mod
from draughtsman.abstract import payload

# `Spec.graph` is the filename, named in the schema as "graph". Everything else
# is expected verbatim.
DESCRIBED_AS = {"src": "from", "dst": "to"}

DATACLASSES = [spec_mod.Spec, spec_mod.Stage, spec_mod.Edge, spec_mod.Layout,
               spec_mod.Lanes, spec_mod.Elision, spec_mod.Meter, spec_mod.Glyph]


def _field_names():
    for cls in DATACLASSES:
        for f in dataclasses.fields(cls):
            yield cls.__name__, DESCRIBED_AS.get(f.name, f.name)


@pytest.mark.parametrize("owner,name",
                         sorted(set(_field_names())),
                         ids=lambda v: v if isinstance(v, str) else str(v))
def test_every_spec_field_is_described_in_the_payload(owner, name, tube_graph):
    """An agent cannot use a field the prompt never mentions."""
    text = payload(tube_graph)
    assert name in text, (
        f"{owner}.{name} exists in the spec format but the `abstract` payload "
        "never mentions it, so no agent answering that prompt can produce it"
    )


def test_the_payload_names_the_shape_problem(tube_graph):
    """Not just the field — the reason. `wrap` in a schema block is a knob; the
    figure being an unreadable ribbon without it is why anyone would turn it."""
    text = payload(tube_graph)
    assert "8:1" in text
    assert "torchview" in text


def test_the_payload_is_honest_that_nothing_checks_the_shape(tube_graph):
    text = payload(tube_graph)
    assert "Coverage is about operations dropped" in text


def test_the_payload_still_forbids_typing_facts(tube_graph):
    """The rule everything else rests on. If a rewrite ever loses this line the
    whole design goes with it."""
    text = payload(tube_graph)
    assert "YOU SUPPLY NO FACTS" in text
    assert "{reference}" in text


def test_the_payload_round_trips_a_spec_that_uses_every_field(tube_graph):
    """A spec exercising each documented field must load, so the payload cannot
    describe a shape the parser would reject."""
    doc = {
        "draughtsman": "0", "graph": "graph.json", "title": "t",
        "subtitle": "s", "caption": "c",
        "layout": {"orientation": "tb", "wrap": 700, "legend": True},
        "stages": [{"id": "a", "name": "A", "kind": "conv", "nodes": [],
                    "detail": ["d"], "note": "n"}],
        "edges": [{"from": "a", "to": "a", "label": "l", "style": "dashed",
                   "untraced": "why"}],
        "elided": [{"nodes": [], "reason": "r"}],
    }
    loaded = spec_mod.load(json.loads(json.dumps(doc)))
    assert loaded.layout.orientation == "tb"
    assert loaded.layout.wrap == 700
    assert loaded.edges[0].untraced == "why"
    assert loaded.stages[0].note == "n"
