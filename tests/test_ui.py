"""`draughtsman ui` — the server contract, and the coupling it depends on.

No browser and no network: these drive `ui.Session` directly, which is where
every decision the UI makes actually lives. Standard library only, so this never
skips.
"""

import json

import pytest

from draughtsman.render import render
from draughtsman.spec import load
from draughtsman.ui import HERE, Session


@pytest.fixture
def session(example_dir, tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text((example_dir / "spec.json").read_text())
    graph = tmp_path / "graph.json"
    graph.write_text((example_dir / "graph.json").read_text())
    return Session(spec, graph)


def test_state_carries_everything_the_page_needs(session):
    s = session.state()
    assert set(s) >= {"spec", "graph", "svg", "check", "paths"}
    assert s["check"]["ok"]
    assert s["svg"].startswith("<svg")
    assert s["paths"]["existed"]


def test_a_failing_spec_is_still_drawn(session):
    """You cannot fix a grouping you cannot see. Coverage failing must not blank
    the figure — it must say so beside it."""
    doc = json.loads(json.dumps(session.spec_doc))
    doc["stages"][1]["nodes"].pop()
    r = session.evaluate(doc)
    assert not r["check"]["ok"]
    assert any("is in no stage" in e for e in r["check"]["errors"])
    assert r["svg"] and r["svg"].startswith("<svg")


def test_an_unanswerable_reference_refuses_rather_than_blanks(session):
    doc = json.loads(json.dumps(session.spec_doc))
    doc["stages"][0]["detail"] = ["{node:n9999.params}"]
    r = session.evaluate(doc)
    assert r["svg"] is None
    assert "n9999" in r["error"]


def test_a_spec_with_no_stages_renders_an_honest_empty_figure(session):
    r = session.evaluate({"draughtsman": "0", "title": "nothing",
                          "stages": [], "edges": []})
    assert r["svg"].startswith("<svg")
    assert "no stages yet" in r["svg"]
    assert len(r["check"]["errors"]) == len(session.graph.traced)


def test_save_writes_both_artifacts_and_agrees_with_the_cli(session):
    """ONE RENDERER. What Save writes must be byte-identical to what
    `draughtsman render` writes, or the figure you judged is not the one that
    ships and SPEC.md §6's staleness test is guarding the wrong thing."""
    out = session.save(session.spec_doc)
    assert len(out["wrote"]) == 2 and out["warning"] is None
    figure = session.spec_path.parent / "figure.svg"
    assert figure.read_text() == render(load(session.spec_doc), session.graph)


def test_opening_a_missing_spec_seeds_one_without_creating_it(tmp_path, example_dir):
    """`draughtsman ui` on a fresh trace has to work, and must not leave a file
    behind just because someone looked."""
    graph = tmp_path / "graph.json"
    graph.write_text((example_dir / "graph.json").read_text())
    s = Session(tmp_path / "spec.json", graph)
    assert not (tmp_path / "spec.json").exists()
    assert s.spec_doc["stages"] == []
    assert s.spec_doc["title"] == "build_tube"
    assert not s.state()["paths"]["existed"]


def test_every_stage_is_addressable_in_the_svg(session):
    """The page binds a click in the figure back to a stage through data-stage.
    Lose the attribute and the figure silently stops being clickable."""
    svg = session.state()["svg"]
    for stage in session.spec_doc["stages"]:
        assert f'data-stage="{stage["id"]}"' in svg


def test_the_page_and_the_server_agree_on_their_endpoints():
    page = (HERE / "ui.html").read_text()
    for route in ("/api/state", "/api/preview", "/api/save"):
        assert route in page


def test_the_page_needs_no_network(tmp_path):
    """It is served on localhost to a machine that may have no route out, and a
    CDN font that fails to load would resize every box the layout measured."""
    page = (HERE / "ui.html").read_text()
    for bad in ("http://", "https://", "//cdn", "@import"):
        assert bad not in page.replace("http://127.0.0.1", "")


def test_the_badge_reads_the_servers_count_and_never_its_own(session):
    """SPEC.md §5's arithmetic has one implementation. A second one in the browser
    is how a badge comes to say 48/47 while the panel beneath it says 47."""
    chk = session.state()["check"]
    assert chk["counts"]["traced"] == 47
    assert chk["counts"]["exactly_once"] == 47
    assert chk["counts"]["untraced_claimed"] == 1
    assert chk["summary"] == "47/47 in exactly one place"

    page = (HERE / "ui.html").read_text()
    assert "chk.summary" in page, "the badge must display the server's summary"
    assert "function coverage(" not in page, \
        "the page is counting coverage again — it must not"


def test_a_double_placed_node_reaches_the_page_as_a_failure(session):
    doc = json.loads(json.dumps(session.spec_doc))
    doc["stages"][2]["nodes"].append(doc["stages"][1]["nodes"][0])
    chk = session.evaluate(doc)["check"]
    assert not chk["ok"]
    assert chk["counts"]["duplicated"] == 1
    assert "in two" in chk["summary"]


def test_export_ships_the_servers_svg_not_a_re_serialisation():
    """Copy/Download SVG must hand over the exact string `render()` produced —
    the same bytes Save writes and the staleness test asserts. Re-serialising the
    DOM would introduce a third representation of the figure, differing from the
    committed one in whatever the browser normalises."""
    page = (HERE / "ui.html").read_text()
    assert "lastSvg" in page
    assert "XMLSerializer" not in page, \
        "export is re-serialising the DOM instead of shipping the rendered string"


def test_the_export_menu_exists_and_offers_the_formats_a_figure_needs():
    page = (HERE / "ui.html").read_text()
    for control in ("x-copy", "x-svg", "x-png1", "x-png2", "x-png4", "x-spec"):
        assert f'id="{control}"' in page


def test_png_export_paints_a_ground():
    """The figure deliberately ships no background — it inherits the embedding
    page (SPEC.md §4). A PNG has no page, so the export has to supply one or the
    text lands on transparency and reads as black-on-black wherever it is pasted.
    """
    page = (HERE / "ui.html").read_text()
    assert "fillRect" in page and "#ffffff" in page


def test_export_says_so_when_coverage_is_failing(session):
    """Exporting a figure that fails coverage is exactly what every tool in §2
    did. It is allowed — you may want it mid-edit — but never silent."""
    page = (HERE / "ui.html").read_text()
    assert "Coverage is failing" in page
    assert "lastOk" in page


# --------------------------------------------------------------------------------
# Many models. SPEC.md §8.4 deferred this; nine models arriving at once is what
# made it concrete.

def test_a_directory_is_one_model_per_folder(example_dir):
    from draughtsman.ui import discover
    found = discover([example_dir.parent])
    names = [m.name for m in found]
    assert "tube" in names
    assert len(names) == len(set(names)), "a model was discovered twice"
    for m in found:
        assert m.graph_path.exists()
        assert m.spec_path == m.graph_path.parent / "spec.json"


def test_a_single_spec_still_opens_exactly_one_model(example_dir):
    """The one-model form is what the CLI has always taken. Adding directories
    must not change what `draughtsman ui spec.json` does."""
    from draughtsman.ui import discover
    found = discover([example_dir / "spec.json"])
    assert len(found) == 1 and found[0].name == "tube"


def test_a_spec_that_does_not_exist_yet_is_still_a_model(tmp_path, example_dir):
    from draughtsman.ui import discover
    (tmp_path / "graph.json").write_text((example_dir / "graph.json").read_text())
    found = discover([tmp_path / "spec.json"])
    assert len(found) == 1
    assert found[0].graph_path == tmp_path / "graph.json"


def test_the_gallery_renders_every_model(example_dir):
    from draughtsman.ui import Workspace, discover
    w = Workspace(discover([example_dir.parent]))
    cards = w.gallery()
    assert len(cards) == len(w.models)
    for c in cards:
        assert c["svg"] and c["svg"].startswith("<svg"), \
            f"{c['name']} did not render: {c['error']}"
        assert c["ok"], f"{c['name']} fails coverage: {c['summary']}"


def test_one_broken_model_does_not_blank_the_sheet(tmp_path, example_dir):
    """Looking at nine at once is the point; one unreadable folder must cost you
    that one card, not the view."""
    from draughtsman.ui import Model, Workspace
    good = Model("good", example_dir / "spec.json", example_dir / "graph.json")
    (tmp_path / "graph.json").write_text("{ not json")
    bad = Model("bad", tmp_path / "spec.json", tmp_path / "graph.json")
    cards = {c["name"]: c for c in Workspace([good, bad]).gallery()}
    assert cards["good"]["ok"] and cards["good"]["svg"]
    assert not cards["bad"]["ok"] and cards["bad"]["error"]


def test_switching_models_keeps_each_ones_session(example_dir):
    from draughtsman.ui import Workspace, discover
    w = Workspace(discover([example_dir.parent]))
    names = [m.name for m in w.models]
    first, second = names[0], names[1]
    a = w.session(first)
    w.session(second)
    assert w.current == second
    assert w.session(first) is a, "reopening a model rebuilt its session"


def test_state_names_the_model_and_lists_the_others(example_dir):
    from draughtsman.ui import Workspace, discover
    w = Workspace(discover([example_dir.parent]))
    st = w.session().state()
    assert st["name"] == w.models[0].name
    page = (HERE / "ui.html").read_text()
    assert 'id="model"' in page and "/api/gallery" in page


def test_trace_without_torch_explains_rather_than_traces(monkeypatch, capsys):
    """torch is deliberately not a hard dependency, so being without it is the
    EXPECTED state for anyone who only draws figures. A stack trace tells them
    they broke something; they did not."""
    import draughtsman.cli as cli

    def no_torch(*a, **kw):
        raise ModuleNotFoundError("No module named 'torch'", name="torch")

    monkeypatch.setattr("draughtsman.tracing.trace", no_torch)
    with pytest.raises(SystemExit) as exc:
        cli.main(["trace", "pkg:build", "--input-shape", "1,3"])
    said = str(exc.value)
    assert "not installed" in said
    assert "draughtsman[trace]" in said
    assert "Traceback" not in said


def test_a_missing_module_that_is_not_torch_still_raises(monkeypatch):
    """Only torch gets the friendly message. Anything else is a real bug and
    must not be dressed up as a missing optional dependency."""
    import draughtsman.cli as cli

    def other(*a, **kw):
        raise ModuleNotFoundError("No module named 'numpy'", name="numpy")

    monkeypatch.setattr("draughtsman.tracing.trace", other)
    with pytest.raises(ModuleNotFoundError):
        cli.main(["trace", "pkg:build", "--input-shape", "1,3"])
