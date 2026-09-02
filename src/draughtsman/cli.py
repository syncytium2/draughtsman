"""``draughtsman`` — four verbs, one per stage plus the check.

    draughtsman trace    mypkg.nets:build_tube --input-shape 1,30,600 -o graph.json
    draughtsman abstract graph.json -o spec.json
    draughtsman render   spec.json -o figure.svg
    draughtsman check    spec.json graph.json
    draughtsman ui       spec.json                  # the human step, in a browser
    draughtsman ui       examples/                  # ... across every model there
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from draughtsman import __version__
from draughtsman.facts import FactError, Graph


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        sys.exit(f"draughtsman: no such file: {path}")
    except json.JSONDecodeError as exc:
        sys.exit(f"draughtsman: {path} is not valid JSON: {exc}")


def _write(path: Path | None, text: str) -> None:
    if path is None:
        sys.stdout.write(text)
    else:
        path.write_text(text)
        print(f"wrote {path}", file=sys.stderr)


def cmd_trace(args) -> int:
    from draughtsman.tracing import dumps, trace
    shapes = [[int(v) for v in spec.split(",")] for spec in args.input_shape]
    try:
        doc = trace(args.target, shapes, dtype=args.dtype or "float32")
    except ValueError as exc:
        sys.exit(f"draughtsman: {exc}")
    except ModuleNotFoundError as exc:
        # torch is deliberately not a hard dependency, so being without it is the
        # EXPECTED state for anyone who only draws figures. A stack trace tells
        # them they broke something; they did not.
        if exc.name != "torch":
            raise
        sys.exit(
            "draughtsman: `trace` needs PyTorch, and it is not installed.\n"
            "    pip install 'draughtsman[trace]'\n"
            "`check` and `render` need nothing at all and work as they are — "
            "torch is only for reading a model."
        )
    _write(args.output, dumps(doc))
    c = doc["classification"]
    print(f"{c['nodes_total']} nodes, {c['nodes_substantive']} substantive, "
          f"{doc['model']['params']} parameters", file=sys.stderr)
    if not doc["params_fully_attributed"]:
        print(f"warning: only {doc['params_attributed']} of "
              f"{doc['model']['params']} parameters could be attributed to a "
              "node; the rest can never appear in a figure", file=sys.stderr)
    return 0


def cmd_abstract(args) -> int:
    from draughtsman.abstract import payload
    graph = Graph(_read(args.graph))
    out = args.output
    # SPEC.md §8.3: the spec is hand-editable, so a re-run must never eat an edit.
    if out is not None and out.exists() and not args.force:
        sys.exit(f"draughtsman: {out} already exists. It may carry hand edits "
                 "worth more than a second pass — pass --force to overwrite, or "
                 "-o to write elsewhere.")
    sys.stdout.write(payload(graph, out_path=str(out) if out else "spec.json"))
    return 0


def cmd_render(args) -> int:
    from draughtsman.render import render
    from draughtsman.spec import load
    spec = load(_read(args.spec))
    gpath = args.graph or (args.spec.parent / spec.graph)
    graph = Graph(_read(gpath))
    if args.check:
        from draughtsman.check import check, report
        result = check(spec, graph)
        if not result.ok:
            print(report(result), file=sys.stderr)
            sys.exit("draughtsman: refusing to render a spec that fails coverage "
                     "(pass --no-check to render it anyway)")
    try:
        svg = render(spec, graph)
    except FactError as exc:
        sys.exit(f"draughtsman: {exc}")
    _write(args.output, svg)
    return 0


def cmd_check(args) -> int:
    from draughtsman.check import check, report
    from draughtsman.spec import load
    spec = load(_read(args.spec))
    gpath = args.graph or (args.spec.parent / spec.graph)
    result = check(spec, Graph(_read(gpath)))
    print(report(result))
    return 0 if result.ok else 1


def cmd_ui(args) -> int:
    from draughtsman.ui import Model, discover, serve
    if args.graph:
        # explicit pair, the single-model form
        models = [Model(name=args.paths[0].parent.name, spec_path=args.paths[0],
                        graph_path=args.graph)]
    else:
        models = discover(args.paths)
    if not models:
        sys.exit("draughtsman: found no graph.json under "
                 + ", ".join(str(p) for p in args.paths)
                 + ". Run `draughtsman trace` first, or pass -g.")
    missing = [m for m in models if not m.graph_path.exists()]
    if missing:
        sys.exit("draughtsman: no graph at "
                 + ", ".join(str(m.graph_path) for m in missing))
    serve(models, port=args.port, open_browser=args.open)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="draughtsman", description=__doc__,
                               formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("trace", help="stage 1 — model to graph.json (facts)")
    t.add_argument("target", help="package.module:callable returning an nn.Module")
    # Repeatable, in the order forward() takes them. An encoder-decoder needs two.
    t.add_argument("--input-shape", required=True, action="append",
                   metavar="N,N,N",
                   help="comma-separated, e.g. 1,30,600. Repeat once per input, "
                        "in the order forward() takes them.")
    t.add_argument("--dtype", action="append", metavar="NAME",
                   help="one for all inputs, or one per --input-shape "
                        "(default float32)")
    t.add_argument("-o", "--output", type=Path)
    t.set_defaults(func=cmd_trace)

    a = sub.add_parser("abstract", help="stage 2 — print the prompt for the agent")
    a.add_argument("graph", type=Path)
    a.add_argument("-o", "--output", type=Path,
                   help="where the answer should be written (not written here)")
    a.add_argument("--force", action="store_true",
                   help="proceed even if the output spec already exists")
    a.set_defaults(func=cmd_abstract)

    r = sub.add_parser("render", help="stage 3 — spec.json + graph.json to SVG")
    r.add_argument("spec", type=Path)
    r.add_argument("-g", "--graph", type=Path)
    r.add_argument("-o", "--output", type=Path)
    r.add_argument("--no-check", dest="check", action="store_false",
                   help="render even if coverage fails")
    r.set_defaults(func=cmd_render, check=True)

    c = sub.add_parser("check", help="§5 coverage — every node in exactly one stage")
    c.add_argument("spec", type=Path)
    c.add_argument("graph", type=Path, nargs="?")
    c.set_defaults(func=cmd_check)

    u = sub.add_parser("ui", help="review and edit a spec in a browser")
    u.add_argument("paths", type=Path, nargs="+", metavar="PATH",
                   help="a spec.json, a graph.json, or a directory to search "
                        "for models (one folder per model). A spec need not "
                        "exist yet; nothing is written until you press Save")
    u.add_argument("-g", "--graph", type=Path)
    u.add_argument("--port", type=int, default=8731)
    u.add_argument("--no-open", dest="open", action="store_false",
                   help="do not open a browser")
    u.set_defaults(func=cmd_ui, open=True)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
