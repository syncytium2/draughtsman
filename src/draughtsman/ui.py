"""`draughtsman ui` — the human step, given a surface.

SPEC.md §5 ends by saying what coverage does not verify: "that the names are good,
the grouping is natural, or the figure is legible. Those need a human." Until now
the human's surface was a JSON file and a rasteriser.

ONE RENDERER. Every picture this serves comes from :func:`draughtsman.render.render`
— the same function the CLI calls and the same one the staleness test asserts
against. A browser-side re-implementation would be quicker to write and would mean
the figure you judged was never the figure that shipped.

EDITS LAND ON DISK. Save writes `spec.json`, and `figure.svg` beside it, because
both are committed artifacts (SPEC.md §6) and a repo where one has moved without
the other is a repo whose staleness test is about to fail for the wrong reason.
A review surface that cannot save is a surface whose work is thrown away, which
is the opposite of SPEC.md §8.3.

Standard library only. It binds to localhost and writes exactly two paths, both
named on the command line.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from draughtsman.check import check, summary
from draughtsman.facts import FactError, Graph
from draughtsman.render import render
from draughtsman.spec import load

HERE = Path(__file__).parent


@dataclass
class Model:
    """One model's three files. `name` is what the picker shows."""
    name: str
    spec_path: Path
    graph_path: Path


def discover(paths: list[Path], *, max_depth: int = 3) -> list[Model]:
    """Every model under *paths*, in a stable order.

    A directory is searched for `graph.json`; the model is named for the folder
    holding it, and its spec is the `spec.json` beside it — which need not exist
    yet. A file is taken as one model directly. This is the convention
    `examples/tube/` already follows, so nine models are nine folders.
    """
    found: dict[str, Model] = {}

    def add(graph: Path, name: str) -> None:
        found.setdefault(name, Model(name=name, graph_path=graph,
                                     spec_path=graph.parent / "spec.json"))

    for path in paths:
        if path.is_dir():
            for depth in range(max_depth + 1):
                for graph in sorted(path.glob("/".join(["*"] * depth + ["graph.json"]))):
                    rel = graph.parent.relative_to(path)
                    add(graph, str(rel) if str(rel) != "." else path.name)
        elif path.name == "graph.json":
            add(path, path.parent.name)
        elif path.exists():
            # a spec: the graph is whatever it names
            graph = path.parent / load(json.loads(path.read_text())).graph
            found.setdefault(path.parent.name, Model(
                name=path.parent.name, spec_path=path, graph_path=graph))
        else:
            # a spec that does not exist yet, beside a graph that does
            found.setdefault(path.parent.name, Model(
                name=path.parent.name, spec_path=path,
                graph_path=path.parent / "graph.json"))
    return [found[k] for k in sorted(found)]


class Session:
    """Paths, the graph, and whatever the browser last sent."""

    def __init__(self, spec_path: Path, graph_path: Path, name: str = ""):
        self.name = name or spec_path.parent.name
        self.spec_path = spec_path
        self.graph_path = graph_path
        self.graph = Graph(json.loads(graph_path.read_text()))
        if spec_path.exists():
            self.spec_doc = json.loads(spec_path.read_text())
            self.existed = True
        else:
            # Started from a graph with nothing grouped yet. Nothing is written
            # until Save, so this cannot create a file by being opened.
            self.spec_doc = {
                "draughtsman": "0",
                "graph": graph_path.name,
                "title": self.graph.model["target"].rpartition(":")[2],
                "stages": [],
                "edges": [],
            }
            self.existed = False

    def evaluate(self, doc: dict) -> dict:
        """Render and check a candidate spec without touching disk."""
        try:
            spec = load(doc)
        except (KeyError, TypeError) as exc:
            return {"svg": None, "error": f"spec is malformed: {exc}",
                    "check": None}
        result = check(spec, self.graph)
        payload = {
            "check": {
                "ok": result.ok,
                "errors": result.errors,
                "warnings": result.warnings,
                "notes": result.notes,
                # The badge displays these. It does not recompute them: a second
                # implementation of §5 is how an indicator comes to disagree with
                # the check it indicates.
                "counts": result.counts.as_dict(),
                "summary": summary(result.counts),
            },
        }
        try:
            # Render even when coverage fails: you cannot fix a grouping you
            # cannot see. The panel says loudly that it does not pass.
            payload["svg"] = render(spec, self.graph)
            payload["error"] = None
        except FactError as exc:
            payload["svg"] = None
            payload["error"] = str(exc)
        return payload

    def save(self, doc: dict) -> dict:
        spec = load(doc)
        self.spec_path.write_text(json.dumps(doc, indent=2,
                                             ensure_ascii=False) + "\n")
        figure = self.spec_path.parent / "figure.svg"
        wrote = [str(self.spec_path)]
        try:
            figure.write_text(render(spec, self.graph))
            wrote.append(str(figure))
        except FactError as exc:
            return {"wrote": wrote, "warning":
                    f"spec saved; figure not written: {exc}"}
        self.spec_doc = doc
        self.existed = True
        return {"wrote": wrote, "warning": None}

    def state(self) -> dict:
        out = self.evaluate(self.spec_doc)
        out["spec"] = self.spec_doc
        out["graph"] = self.graph.doc
        out["paths"] = {"spec": str(self.spec_path),
                        "graph": str(self.graph_path),
                        "existed": self.existed}
        out["name"] = self.name
        return out

    def card(self) -> dict:
        """What the gallery shows for this model: the figure, and whether it is
        finished. Rendering all of them is how a layout defect in one of nine
        becomes visible without opening nine tabs."""
        r = self.evaluate(self.spec_doc)
        return {
            "name": self.name,
            "title": self.spec_doc.get("title", self.name),
            "svg": r["svg"],
            "error": r["error"],
            "ok": bool(r["check"] and r["check"]["ok"]),
            "summary": (r["check"] or {}).get("summary", ""),
            "stages": len(self.spec_doc.get("stages", [])),
            "params": self.graph.model["params"],
            "started": self.existed,
        }


class Workspace:
    """Every model the UI was pointed at, and which one is open."""

    def __init__(self, models: list[Model]):
        if not models:
            raise ValueError("no models found")
        self.models = models
        self._open: dict[str, Session] = {}
        self.current = models[0].name

    def session(self, name: str | None = None) -> Session:
        name = name or self.current
        if name not in {m.name for m in self.models}:
            raise KeyError(name)
        if name not in self._open:
            m = next(m for m in self.models if m.name == name)
            self._open[name] = Session(m.spec_path, m.graph_path, m.name)
        self.current = name
        return self._open[name]

    def gallery(self) -> list[dict]:
        cards = []
        for m in self.models:
            try:
                cards.append(self.session(m.name).card())
            except Exception as exc:                  # noqa: BLE001
                # One unreadable model must not blank the sheet — that is the
                # whole reason for looking at nine at once.
                cards.append({"name": m.name, "title": m.name, "svg": None,
                              "error": str(exc), "ok": False, "summary": "",
                              "stages": 0, "params": 0, "started": False})
        return cards


class Handler(BaseHTTPRequestHandler):
    workspace: Workspace = None        # set by serve()
    server_version = "draughtsman"

    def _model(self) -> str | None:
        q = parse_qs(urlparse(self.path).query)
        return (q.get("model") or [None])[0]

    def log_message(self, fmt, *args):  # the browser polls; stay quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        route = urlparse(self.path).path
        if route in ("/", "/index.html"):
            self._send(200, (HERE / "ui.html").read_bytes(),
                       "text/html; charset=utf-8")
        elif route == "/api/state":
            try:
                st = self.workspace.session(self._model()).state()
            except KeyError as exc:
                self._json({"error": f"no model {exc}"}, 404)
                return
            st["models"] = [m.name for m in self.workspace.models]
            self._json(st)
        elif route == "/api/gallery":
            self._json({"models": self.workspace.gallery()})
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        try:
            body = self._read_json()
        except json.JSONDecodeError as exc:
            self._json({"error": f"bad JSON: {exc}"}, 400)
            return
        route = urlparse(self.path).path
        try:
            session = self.workspace.session(body.get("model") or self._model())
        except KeyError as exc:
            self._json({"error": f"no model {exc}"}, 404)
            return
        if route == "/api/preview":
            self._json(session.evaluate(body.get("spec", {})))
        elif route == "/api/save":
            try:
                self._json(session.save(body.get("spec", {})))
            except Exception as exc:                  # noqa: BLE001 — report it
                self._json({"error": str(exc)}, 400)
        else:
            self._send(404, b"not found", "text/plain")


def serve(models: list[Model], *, port: int = 8731,
          open_browser: bool = True) -> None:
    Handler.workspace = Workspace(models)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{httpd.server_port}/"
    print(f"draughtsman ui — {url}")
    for m in models:
        mark = "" if m.spec_path.exists() else "  (no spec yet)"
        print(f"  {m.name:<24} {m.graph_path.parent}{mark}")
    print(f"  {len(models)} model(s). Save writes spec.json and figure.svg "
          "beside each. Ctrl-C to stop.")
    if open_browser:
        threading.Timer(0.4, webbrowser.open, (url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
